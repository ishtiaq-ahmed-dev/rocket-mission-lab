"""Classical guidance and gimbal tracking on exactly the same RocketEnv."""
import numpy as np

class ClassicalController:
    def __init__(self, level=4):
        self.level = level
        self.plan = None
        self.plan_phase = None
        self.plan_status = "not_requested"
        self.lqr_gain = None
        self.velocity_integral=0.
        self.attitude_integral=np.zeros(3)
        self.engine_on=True
        self.estimate=None

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

    def action(self, env):
        ph=env.physics
        s, cfg=getattr(env,"sensed_state",ph.state()), env.cfg
        if self.level>=3:
            measured=s
            if self.estimate is not None and s['t']>self.estimate['t']:
                dt=s['t']-self.estimate['t']
                predicted=self.estimate['position']+self.estimate['velocity']*dt
                s={**s,'position':predicted+.18*(s['position']-predicted),
                   'velocity':self.estimate['velocity']+.4*(s['velocity']-self.estimate['velocity'])}
            self.estimate={**measured,'position':s['position'].copy(),'velocity':s['velocity'].copy()}
        velocity, position=s["velocity"], s["position"]
        h=float(position[2]-ph.half)
        lateral_error=position[:2]-env._target()[:2]
        # Keep a clearance shelf during long transfers. The governor bounds the
        # lateral step presented to LQR, avoiding gimbal saturation and flips.
        transfer=np.linalg.norm(lateral_error)>12 and env.phase=='landing'
        guidance_height=h-(60. if transfer else 0.)
        g=cfg["world"]["gravity"]
        if self.level==1:
            # Deliberately untuned altitude/attitude gains, a real failing baseline.
            target_speed=-0.25*h if env.phase=="landing" else 20
            az = 0.12*(target_speed-velocity[2])
        elif env.phase=="takeoff":
            target_speed=min(env.takeoff_velocity, 5+0.12*h)
            az=np.clip(1.1*(target_speed-velocity[2]), -5, 6)
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
            rho=cfg["world"]["density_sea_level"]*np.exp(-max(0,h)/cfg["world"]["scale_height"])
            drag=-0.5*rho*cfg["vehicle"]["drag_coefficient"]*cfg["vehicle"]["area"]*np.linalg.norm(rel)*rel
            lateral-=drag[:2]/s["mass"]
            az-=drag[2]/s["mass"]
            if env.phase=="landing":
                # Feed forward the derivative of the altitude-dependent speed
                # reference. Without this term, feedback alone lags touchdown.
                href=max(0.,guidance_height)
                candidates=[28.,np.sqrt(3*href+.25),.25*href+.35]
                which=int(np.argmin(candidates))
                reference=-candidates[which] if guidance_height>=0 else min(3.,-guidance_height*.5)
                if transfer and guidance_height<2:reference=np.clip(-guidance_height*.5,-2,3)
                target_speed=reference
                derivative=0. if which==0 else (-1.5/max(np.sqrt(3*href+.25),.1) if which==1 else -.25)
                az=np.clip(derivative*velocity[2]+2*(reference-velocity[2])-drag[2]/s["mass"],-8,12)
        lateral=np.clip(lateral,-1.0,1.0)
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
        if env.phase=="landing" and velocity[2]>2 and h>100:
            thrust=0 # ballistic coast after combined mission separation
        throttle=thrust/ph.v["max_thrust"]
        if self.level==1: throttle*=0.72
        denom=max(thrust*ph.half,1)
        gx,gy=-torque_body[1]/denom,torque_body[0]/denom
        if self.level==4:
            # LQR stabilizes the complete lateral/attitude chain, including the
            # initially adverse translation produced by engine gimbal torque.
            if self.lqr_gain is None:
                from scipy.linalg import solve_continuous_are
                a=np.array([[0,1,0,0],[0,0,g,0],[0,0,0,1],[0,0,0,0.]])
                b=np.array([[0],[g],[0],[-g*s["mass"]*ph.half/ph.model.body_inertia[1,0]]])
                q=np.diag([.01,.4,10,3]); rr=np.array([[20.]])
                self.lqr_gain=np.linalg.solve(rr,b.T@solve_continuous_are(a,b,q,rr))[0]
            n_dot=rot@np.cross(s["angular_velocity"],[0.,0.,1.])
            desired_gimbal=[]
            for axis in range(2):
                state=[np.clip(lateral_error[axis],-12.,12.),velocity[axis],n[axis],n_dot[axis]]
                desired_gimbal.append(-float(self.lqr_gain@state))
            body_gimbal=rot.T@np.array([*desired_gimbal,0.])
            gx,gy=body_gimbal[:2]
        limit=np.deg2rad(ph.v["gimbal_limit_deg"])
        if self.level>=3 and 0<throttle<ph.v['min_throttle']:
            # Below the engine floor use velocity hysteresis, with a real off
            # command. Clamping every request to minimum thrust causes a light
            # booster to climb indefinitely as its mass falls.
            if velocity[2]>target_speed+.5:self.engine_on=False
            elif velocity[2]<target_speed-.5:self.engine_on=True
            throttle=ph.v['min_throttle'] if self.engine_on else 0.
        return np.clip([2*throttle-1,gx/limit,gy/limit],-1,1).astype(np.float32)
