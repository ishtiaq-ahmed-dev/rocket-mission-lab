"""Classical guidance and gimbal tracking on exactly the same RocketEnv."""
import numpy as np
from .atmosphere import air_density

class ClassicalController:
    def __init__(self, level=4):
        self.level = level
        self.plan = None
        self.plan_phase = None
        self.plan_status = "not_requested"
        self.lqr_gain = None
        self.lqr_acceleration = None
        self.velocity_integral=0.
        self.attitude_integral=np.zeros(3)
        self.engine_on=True
        self.estimate=None
        self.cruise_speed=25. # m/s bound on lateral divert speed
        self.brake_decel=1.2 # m/s^2 braking profile, below the tilt-limited capability
        self.velocity_clip=5. # m/s bound on the velocity error presented to LQR
        self.fade_radius=40. # m, beyond this only the velocity profile is tracked
        self.glide_slope=2. # m of clearance per m of remaining lateral distance
        self.max_shelf=120. # m
        self.divert=False
        self.recovery_burn=False
        self.terminal_captured=False

    def on_retarget(self):
        """Recompute guidance for a new landing target without resetting the vehicle."""
        self.plan=None
        self.plan_phase=None
        self.plan_status="replanned_for_new_target"
        self.velocity_integral=0.
        self.attitude_integral=np.zeros(3)
        self.engine_on=True
        # A mid-air target change is a divert: hold a safe altitude while the
        # booster flies laterally, then resume the terminal descent. Without
        # this, the normal descent profile reaches the old altitude too early
        # and the lateral correction becomes unreachable.
        self.divert=True

    def _solve_descent(self, env):
        import cvxpy as cp
        s, cfg = env.physics.state(), env.cfg
        p0 = np.asarray(s["position"])-env._target()
        v0 = np.asarray(s["velocity"])
        horizon = max(12., min(45., 2*p0[2]/max(abs(v0[2]), 12)))
        n, dt = 40, horizon/40
        p, v, a = cp.Variable((3,n+1)), cp.Variable((3,n+1)), cp.Variable((3,n))
        constraints = [p[:,0]==p0, v[:,0]==v0, p[:,-1]==0, v[:,-1]==[0,0,-0.6], p[2,:]>=-0.01]
        for k in range(n):
            thrust_acc = a[:,k]+[0,0,cfg["world"]["gravity"]]
            constraints += [p[:,k+1]==p[:,k]+v[:,k]*dt+0.5*a[:,k]*dt**2,
                            v[:,k+1]==v[:,k]+a[:,k]*dt,
                            cp.norm(thrust_acc)<=cfg["vehicle"]["max_thrust"]/s["mass"]*0.95,
                            thrust_acc[2]>=0, cp.norm(thrust_acc[:2])<=0.15*thrust_acc[2]]
        # Constant-mass convex approximation, relaxed lower thrust bound.
        problem=cp.Problem(cp.Minimize(cp.sum_squares(a)+0.02*cp.sum_squares(v)), constraints)
        try:
            problem.solve(solver="CLARABEL")
            self.plan_status=problem.status
            if problem.status in ("optimal", "optimal_inaccurate"):
                self.plan=(s["t"], dt, p.value, v.value, a.value)
        except cp.error.SolverError:
            self.plan_status="solver_error"

    def _model_acceleration(self, env, s, velocity):
        """Acceleration implied by measured actuator state and the nominal vehicle model."""
        ph,cfg=env.physics,env.cfg
        direction=np.array([np.tan(s['gimbal'][0]),np.tan(s['gimbal'][1]),1.]);direction/=np.linalg.norm(direction)
        force=ph.rotation()@(direction*s['throttle']*ph.v['max_thrust'])
        relative=velocity-s['wind']
        rho=air_density(cfg['world'],s['position'][2]-ph.half)
        drag=-.5*rho*ph.v['drag_coefficient']*ph.v['area']*np.linalg.norm(relative)*relative
        return (force+drag)/s['mass']-np.array([0.,0.,ph.gravity(s['altitude'])])

    def _attitude_acceleration(self, env, s, n):
        """Second derivative of the body axis from the engine-lever torque."""
        ph=env.physics
        direction=np.array([np.tan(s['gimbal'][0]),np.tan(s['gimbal'][1]),1.]);direction/=np.linalg.norm(direction)
        force=direction*s['throttle']*ph.v['max_thrust']
        alpha=ph.rotation()@(np.array([ph.engine_lever*force[1],-ph.engine_lever*force[0],0.])/ph.model.body_inertia[1,0])
        return np.cross(alpha,n)

    def action(self, env):
        ph=env.physics
        s, cfg=getattr(env,"sensed_state",ph.state()), env.cfg
        if self.level>=3:
            # Model-aided navigation filter: engine/gimbal feedback and the vehicle model predict
            # acceleration, so the noisy velocity measurement only corrects slow model error.
            measured=s;n=ph.rotation()[:,2].copy();previous=self.estimate
            if previous is not None and s['t']>previous['t']:
                dt=s['t']-previous['t']
                accel_now=self._model_acceleration(env,measured,previous['velocity'])
                accel=.5*(previous['accel']+accel_now)
                velocity_prediction=previous['velocity']+accel*dt
                position_prediction=previous['position']+previous['velocity']*dt+.5*accel*dt*dt
                s={**s,'position':position_prediction+np.array([.08,.08,.18])*(measured['position']-position_prediction),
                   'velocity':velocity_prediction+np.array([.12,.12,.3])*(measured['velocity']-velocity_prediction)}
                # Attitude is exact; its finite difference plus the known gimbal torque replaces the noisy gyro.
                s['n_dot']=(n-previous['n'])/dt+.5*dt*self._attitude_acceleration(env,measured,n)
            else:s={**s,'n_dot':ph.rotation()@np.cross(s['angular_velocity'],[0.,0.,1.])}
            self.estimate={**measured,'position':s['position'].copy(),'velocity':s['velocity'].copy(),'n':n,'n_dot':s['n_dot'],
                           'accel':self._model_acceleration(env,measured,s['velocity'])}
        velocity, position=s["velocity"], s["position"]
        h=float(position[2]-ph.half)
        lateral_error=position[:2]-env._target()[:2]
        # Approach cone: the vehicle stays above a glide slope toward the target, so lateral
        # transfers use descent time instead of hovering, and it never aims below the capture cone.
        shelf=min(self.max_shelf,self.glide_slope*max(float(np.linalg.norm(lateral_error))-12.,0.)) if env.phase=='landing' else 0.
        can_hover=1.03*ph.v['min_throttle']*ph.v['max_thrust']<s['mass']*ph.gravity(h)
        capture_height=100 if cfg['mission'].get('high_altitude_recovery') else 50
        if self.level==4 and can_hover and env.phase=='landing' and h<capture_height:
            if np.linalg.norm(lateral_error)<.35 and np.linalg.norm(velocity[:2])<.15 and s['tilt']<1:
                self.terminal_captured=True
            if not self.terminal_captured:shelf=max(shelf,35. if cfg['mission'].get('high_altitude_recovery') else 20.)
        transfer=shelf>0
        guidance_height=h-shelf
        g=ph.gravity(h)
        if self.level==1:
            # Deliberately untuned altitude/attitude gains, a real failing baseline.
            target_speed=-0.25*h if env.phase=="landing" else 20
            az = 0.12*(target_speed-velocity[2])
        elif env.phase=="takeoff":
            target_speed=min(env.takeoff_velocity, 5+0.12*h)
            az=np.clip(1.1*(target_speed-velocity[2]), -5, cfg['mission'].get('takeoff_acceleration',6))
        else:
            target_speed=-min(28., np.sqrt(max(0., 3.0*h)), 0.5*max(h,0)+0.65)
            az=np.clip((0.75 if self.level==2 else 1.5)*(target_speed-velocity[2]), -8., 12.)
        if self.level<=2:
            dt=cfg["world"]["timestep"]*cfg["world"]["control_substeps"]
            self.velocity_integral=np.clip(self.velocity_integral+(target_speed-velocity[2])*dt,-2.,2.)
            az+=(.005 if self.level==1 else .03)*self.velocity_integral
        lateral=-0.025*(position[:2]-env._target()[:2])-0.45*velocity[:2]
        if self.level==3 and env.phase=="landing":
            if self.plan_phase!=env.phase:
                self.plan_phase=env.phase
                self._solve_descent(env)
            if self.plan and h>12:
                start,dt,p,v,a=self.plan
                k=min(a.shape[1]-1,int((s["t"]-start)/dt))
                error=p[:,k]+env._target()-position
                desired=a[:,k]+0.08*error+0.8*(v[:,k]-velocity)
                az=float(desired[2]); lateral=desired[:2]
        if self.level==4:
            # Model-based drag feedforward. No external attitude thrusters.
            rel=velocity-s["wind"]
            rho=air_density(cfg['world'],h)
            drag=-0.5*rho*cfg["vehicle"]["drag_coefficient"]*cfg["vehicle"]["area"]*np.linalg.norm(rel)*rel
            lateral-=drag[:2]/s["mass"]
            az-=drag[2]/s["mass"]
            if env.phase=="landing":
                # Feed forward the derivative of the altitude-dependent speed
                # reference. Without this term, feedback alone lags touchdown.
                href=max(0.,guidance_height)
                # The slow exponential flare needs a hover throttle at or above the engine floor. A light booster
                # (floor thrust above weight) must instead keep braking along the 1.5 m/s^2 profile.
                hover_ok=1.03*ph.v['min_throttle']*ph.v['max_thrust']<s['mass']*g
                # Without a hover throttle the vehicle cannot shed speed gently, so it touches down at a
                # firm 1.2 m/s with the engine still burning (cutoff at contact) rather than floating.
                high_recovery=cfg['mission'].get('high_altitude_recovery',False)
                descent_cap=1800. if high_recovery and h>1500 else 28.
                braking=3. if not high_recovery or h<1500 else min(48.,max(3.,(ph.v['max_thrust']/s['mass']-g)*1.0))
                candidates=[descent_cap,np.sqrt(braking*href+.25)] if hover_ok else [descent_cap,max(np.sqrt(braking*href+.25),1.2)]
                if hover_ok:candidates.append(.25*href+.6)
                which=int(np.argmin(candidates))
                reference=-candidates[which] if guidance_height>=0 else min(8.,-guidance_height*.5)
                if transfer and guidance_height<2:reference=np.clip(-guidance_height*.5,-2,8)
                target_speed=reference
                derivative=0. if which==0 or (which==1 and braking*href+.25<1.44 and not hover_ok) else (-braking/2/max(np.sqrt(braking*href+.25),.1) if which==1 else -.25)
                ceiling=max(12.,ph.v['max_thrust']/s['mass']-g) if high_recovery else 12.
                az=np.clip(derivative*velocity[2]+2*(reference-velocity[2])-drag[2]/s["mass"],-8,ceiling)
                if self.divert:
                    distance_now=float(np.linalg.norm(lateral_error))
                    if distance_now<18. or h<18.:
                        self.divert=False
                    else:
                        # Hold a shallow descent during the lateral divert. A
                        # light booster cannot always hover above the engine
                        # floor, so use a real slow descent instead of a climb.
                        reference=-1.0 if hover_ok else -2.4
                        target_speed=reference
                        az=np.clip(2.2*(reference-velocity[2])-drag[2]/s["mass"],-8,12)
        lateral=np.clip(lateral,-1.0,1.0)
        if cfg['mission'].get('high_altitude_recovery') and env.phase=='landing':
            distance=float(np.linalg.norm(lateral_error))
            reference=-lateral_error/max(distance,1e-6)*min(25.,np.sqrt(2*1.2*max(distance-8.,0.)))
            lateral=np.clip(.25*(reference-velocity[:2]),-1.5,1.5) if distance>12 else np.clip(-.06*lateral_error-.6*velocity[:2],-1.5,1.5)
        desired=np.array([*lateral, max(1., g+az)])
        desired/=np.linalg.norm(desired)
        rot=ph.rotation()
        n=rot[:,2]
        omega_world=rot@s["angular_velocity"]
        kp,kd=(0.3,0.5) if self.level==1 else (3.0,3.3)
        torque_world=(kp*np.cross(n,desired)-kd*omega_world)*ph.model.body_inertia[1,0]
        if self.level<=2:
            self.attitude_integral=np.clip(self.attitude_integral+np.cross(n,desired)*cfg["world"]["timestep"]*cfg["world"]["control_substeps"],-.1,.1)
            torque_world+=.05*self.attitude_integral*ph.model.body_inertia[1,0]
        torque_body=rot.T@torque_world
        # Vertical acceleration divided by actual body-axis vertical projection.
        thrust=np.clip(s["mass"]*(g+az)/max(n[2],0.3),0,ph.v["max_thrust"])
        if env.phase=="landing" and env.separated and velocity[2]>2 and h>100:
            thrust=0 # ballistic coast after combined mission separation
        if env.phase=='landing' and cfg['mission'].get('high_altitude_recovery',False) and h>1500:
            # Coast until a stopping-distance envelope calls for an entry burn.
            # No forces, attitude corrections or coordinate changes are hidden
            # in this coast. Ignition/valve lag is included in the margin.
            deceleration=max(1.,ph.v['max_thrust']/s['mass']-g)
            stopping=velocity[2]**2/(2*deceleration*.60)+abs(velocity[2])*1.5+900.
            if velocity[2]<0 and h<=stopping:self.recovery_burn=True
            if not self.recovery_burn:thrust=0.
        throttle=thrust/ph.v["max_thrust"]
        if self.level==1: throttle*=0.72
        denom=max(thrust*ph.engine_lever,1)
        gx,gy=-torque_body[1]/denom,torque_body[0]/denom
        if self.level==4:
            # LQR stabilizes the complete lateral/attitude chain, including the
            # initially adverse translation produced by engine gimbal torque.
            acceleration=max(g,thrust/s['mass']) if cfg['mission'].get('high_altitude_recovery') else g
            schedule=self.lqr_acceleration is None or abs(acceleration/self.lqr_acceleration-1)>.2
            if self.lqr_gain is None or (cfg['mission'].get('high_altitude_recovery') and schedule):
                from scipy.linalg import solve_continuous_are
                a=np.array([[0,1,0,0],[0,0,acceleration,0],[0,0,0,1],[0,0,0,0.]])
                b=np.array([[0],[acceleration],[0],[-acceleration*s["mass"]*ph.engine_lever/ph.model.body_inertia[1,0]]])
                q=np.diag([.04,.4,10,3]); rr=np.array([[20.]])
                self.lqr_gain=np.linalg.solve(rr,b.T@solve_continuous_are(a,b,q,rr))[0]
                self.lqr_acceleration=acceleration
            n_dot=s.get('n_dot',rot@np.cross(s["angular_velocity"],[0.,0.,1.]))
            # Divert governor: far from the target LQR tracks a bounded-acceleration velocity profile
            # (accelerate, cruise, brake) instead of a creeping 12 m position error.
            distance=float(np.linalg.norm(lateral_error))
            capture=12.
            reference=np.zeros(2)
            if distance>capture:
                reference=-lateral_error/distance*min(self.cruise_speed,np.sqrt(2*self.brake_decel*(distance-capture)))
            # The position term fades out beyond the capture radius, so it cannot fight the braking profile.
            error_command=lateral_error*float(np.clip((self.fade_radius-distance)/(self.fade_radius-capture),0.,1.))
            desired_gimbal=[]
            for axis in range(2):
                state=[error_command[axis],np.clip(velocity[axis]-reference[axis],-self.velocity_clip,self.velocity_clip),n[axis],n_dot[axis]]
                desired_gimbal.append(-float(self.lqr_gain@state))
            body_gimbal=rot.T@np.array([*desired_gimbal,0.])
            gx,gy=body_gimbal[:2]
            if cfg['mission'].get('high_altitude_recovery') and (h>800 or s['tilt']>8):
                # Geometric attitude tracking stays well-defined after a long
                # unpowered coast. The near-hover LQR linearization does not.
                desired_body=rot.T@desired
                omega=rot.T@np.cross(n,s.get('n_dot',np.cross(omega_world,n)))
                inertia=ph.model.body_inertia[1]
                torque=.5*np.cross([0.,0.,1.],desired_body)*inertia[0]-1.4*omega*inertia
                torque+=np.cross(omega,inertia*omega)
                gx,gy=-torque[1]/denom,torque[0]/denom
        limit=np.deg2rad(ph.v["gimbal_limit_deg"])
        if self.level>=3 and 0<throttle<ph.v['min_throttle']:
            # Below the engine floor use velocity hysteresis, with a real off
            # command. Clamping every request to minimum thrust causes a light
            # booster to climb indefinitely as its mass falls.
            # An engine-out gap costs spool-up time; never accept one close to the ground.
            if h<=12.:self.engine_on=True
            elif velocity[2]>target_speed+.5:self.engine_on=False
            elif velocity[2]<target_speed-.5:self.engine_on=True
            throttle=ph.v['min_throttle'] if self.engine_on else 0.
        return np.clip([2*throttle-1,gx/limit,gy/limit],-1,1).astype(np.float32)
