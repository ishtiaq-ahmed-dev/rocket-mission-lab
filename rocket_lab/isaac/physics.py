"""Native USD/PhysX booster. Import only after SimulationApp has started.

The RocketEnv contract is preserved, but PhysX owns pose, velocity, contact,
gravity and both rigid bodies. Fuel exhaust uses F = mdot Isp g0.
"""
from types import SimpleNamespace
import numpy as np
from scipy.spatial.transform import Rotation
from pxr import Gf,PhysxSchema,Sdf,UsdGeom,UsdPhysics,UsdShade
import omni.usd
from isaacsim.core.api import World
from isaacsim.core.api.objects import GroundPlane
from isaacsim.core.api.materials import PhysicsMaterial
from isaacsim.core.prims import RigidPrim
from ..atmosphere import air_density
from .actuators import Engine,RollThrusters,contact_geometry,gravity_at


def xyz(values):return Gf.Vec3f(*map(float,values))


class IsaacRocketPhysics:
    def __init__(self,config,headless=False,gpu_dynamics=False,visuals=None):
        self.cfg=config;self.v=config['vehicle'];self.w=config['world'];self.half=self.v['length']/2
        self.engine_lever=self.v.get('engine_lever',self.half);self.headless=headless;self.visuals=visuals
        self.engine=Engine(self.v,self.w['gravity']);self.rcs=RollThrusters(self.v);self.roll_command=0.;self.data=SimpleNamespace(time=0.)
        # Read-only compatibility values for existing inertia-aware guidance.
        self.model=SimpleNamespace(body_inertia=np.zeros((2,3)))
        self.world=World(stage_units_in_meters=1.,physics_dt=self.w['timestep'],rendering_dt=1/30,backend='numpy',device='cpu')
        context=self.world.get_physics_context();context.set_solver_type('TGS')
        context.enable_gpu_dynamics(gpu_dynamics)
        if gpu_dynamics:context.set_broadphase_type('GPU')
        else:context.enable_ccd(True)
        context.set_gravity(-self.w['gravity']);self._last_gravity=self.w['gravity']
        surface=PhysicsMaterial('/World/GroundContact',static_friction=.8,dynamic_friction=.6,restitution=0.)
        self.world.scene.add(GroundPlane('/World/Ground',size=20000.,z_position=0.,color=np.array([.12,.14,.12]),physics_material=surface))
        self.stage=omni.usd.get_context().get_stage()
        UsdGeom.SetStageUpAxis(self.stage,UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(self.stage,1.)
        self._create_vehicle()
        if visuals:visuals.setup(self)
        self.booster=RigidPrim('/World/Booster',name='booster',reset_xform_properties=False,track_contact_forces=True)
        self.payload=RigidPrim('/World/Payload',name='payload',reset_xform_properties=False)
        self.world.scene.add(self.booster);self.world.scene.add(self.payload)
        print('NATIVE: rigid body views created; initializing PhysX',flush=True)
        self.world.reset()
        print('NATIVE: PhysX initialized; setting mass and poses',flush=True)
        self.reset(0)
        print('NATIVE: physical state initialized',flush=True)

    def _create_vehicle(self):
        for path in ('/World/Booster','/World/Payload'):
            transform=UsdGeom.Xform.Define(self.stage,path)
            transform.AddTranslateOp().Set(Gf.Vec3d(0,0,self.half+200+(self.half+4.5 if path.endswith('Payload') else 0)))
            transform.AddOrientOp().Set(Gf.Quatf(1))
            root=transform.GetPrim()
            UsdPhysics.RigidBodyAPI.Apply(root)
            body=PhysxSchema.PhysxRigidBodyAPI.Apply(root)
            body.CreateSolverPositionIterationCountAttr(16);body.CreateSolverVelocityIterationCountAttr(4)
            body.CreateLinearDampingAttr(0.);body.CreateAngularDampingAttr(0.)
            body.CreateEnableCCDAttr(True)
            mass=UsdPhysics.MassAPI.Apply(root);mass.CreateCenterOfMassAttr(Gf.Vec3f(0))
        hull=UsdGeom.Cylinder.Define(self.stage,'/World/Booster/Hull')
        hull.CreateAxisAttr('Z');hull.CreateRadiusAttr(self.v['radius']);hull.CreateHeightAttr(self.v['length']-6.)
        UsdPhysics.CollisionAPI.Apply(hull.GetPrim())
        for index,(x,y) in enumerate(((6.2,0),(-6.2,0),(0,6.2),(0,-6.2))):
            foot=UsdGeom.Sphere.Define(self.stage,f'/World/Booster/Foot{index}')
            foot.CreateRadiusAttr(.15);foot.AddTranslateOp().Set(Gf.Vec3d(x,y,-self.half+.15))
            UsdPhysics.CollisionAPI.Apply(foot.GetPrim())
        satellite=UsdGeom.Cylinder.Define(self.stage,'/World/Payload/Hull')
        satellite.CreateAxisAttr('Z');satellite.CreateRadiusAttr(1.8);satellite.CreateHeightAttr(9.)
        UsdPhysics.CollisionAPI.Apply(satellite.GetPrim())
        self.stage_joint=None;self.hold_joint=None

    def _joint(self,path,body0,body1,position0,position1):
        # Author a complete constraint atomically. Defining relationships and
        # anchors separately while PhysX is live exposes an incomplete joint.
        with Sdf.ChangeBlock():
            prim=Sdf.CreatePrimInLayer(self.stage.GetEditTarget().GetLayer(),path)
            prim.specifier=Sdf.SpecifierDef;prim.typeName='PhysicsFixedJoint'
            for name,target in (('physics:body0',body0),('physics:body1',body1)):
                if target:Sdf.RelationshipSpec(prim,name,custom=False).targetPathList.explicitItems=[Sdf.Path(target)]
            for name,kind,value in (
                ('physics:localPos0',Sdf.ValueTypeNames.Point3f,xyz(position0)),
                ('physics:localPos1',Sdf.ValueTypeNames.Point3f,xyz(position1)),
                ('physics:localRot0',Sdf.ValueTypeNames.Quatf,Gf.Quatf(1)),
                ('physics:localRot1',Sdf.ValueTypeNames.Quatf,Gf.Quatf(1)),
                ('physics:excludeFromArticulation',Sdf.ValueTypeNames.Bool,True),
                ('physics:collisionEnabled',Sdf.ValueTypeNames.Bool,False),
                ('physics:jointEnabled',Sdf.ValueTypeNames.Bool,True)):
                Sdf.AttributeSpec(prim,name,kind,Sdf.VariabilityVarying,False).default=value
        return UsdPhysics.FixedJoint.Get(self.stage,path)

    @property
    def mass(self):return self.v['dry_mass']*self.mass_scale+self.fuel+self.rcs.fuel+(self.payload_mass if self.attached else 0.)
    @property
    def throttle(self):return self.engine.throttle
    @property
    def gimbal(self):return self.engine.gimbal
    @property
    def thrust(self):return self.engine.thrust

    def _mass_update(self):
        # Each physical body owns its own mass; attached payload is never counted twice.
        mass=self.v['dry_mass']*self.mass_scale+self.fuel+self.rcs.fuel
        inertia=np.asarray(self.v['inertia'])*mass/self.v['dry_mass']
        self.booster.set_masses(np.array([mass],dtype=np.float32))
        self.booster.set_inertias(np.diag(inertia).reshape(1,9).astype(np.float32))
        self.model.body_inertia[1]=inertia

    def reset(self,seed,position=None,velocity=None,quaternion=None,mass_scale=1.,wind_scale=1.,thrust_scale=1.):
        # A pose teleport alone preserves PhysX contact warm-start/constraint
        # state from the previous landing. Rebuild the simulation view between
        # episodes so evaluation order cannot change the next flight.
        # Remove live constraints before timeline stop restores its edit layer.
        # Otherwise the previous flight's joint can be rebuilt between poses.
        for path in ('/World/PayloadConnector','/World/LaunchHoldDown'):
            if self.stage.GetPrimAtPath(path):self.stage.RemovePrim(path)
        self.stage_joint=None;self.hold_joint=None
        self.world.stop()
        self.rng=np.random.default_rng(seed);self.mass_scale=mass_scale;self.wind_scale=wind_scale;self.thrust_scale=thrust_scale
        self.fuel=self.v['fuel_mass']*mass_scale;self.payload_mass=self.v.get('upper_stage_mass',2500.)*mass_scale
        self.attached=self.v.get('upper_stage_mass',0)>0;self.hold_elapsed=0.;self.release_time=None;self.data.time=0.
        self.engine.reset();self.rcs.reset();self.roll_command=0.;self.wind=np.asarray(self.w['wind_mean'],dtype=float)*wind_scale
        self._impacted=False;self._impact_speed=0.;self._render_step=0;self.detached=False
        self.impact_state=None
        self.separation_time=None;self.separation_axis=np.zeros(3)
        p=np.asarray(position if position is not None else [0.,0.,self.half+200.],dtype=float)
        v=np.asarray(velocity if velocity is not None else [0.,0.,-20.],dtype=float)
        q=np.asarray(quaternion if quaternion is not None else [1.,0.,0.,0.],dtype=float)
        self.on_pad=bool(p[2]<=self.half+.1 and np.linalg.norm(v)<1e-6)
        self._contact_armed=not self.on_pad
        if self.on_pad:q=np.array([1.,0.,0.,0.]);p[2]=self.half
        if self.stage_joint:
            self.stage.RemovePrim('/World/PayloadConnector');self.stage_joint=None
        if self.hold_joint:
            self.stage.RemovePrim('/World/LaunchHoldDown');self.hold_joint=None
        rotation=Rotation.from_quat([*q[1:],q[0]]).as_matrix();stage_position=p+rotation@np.array([0,0,self.half+4.5])
        # Keep authored reset poses consistent with the tensor state. Creating a
        # renderer/collider/joint can make PhysX re-read USD on the next frame.
        with Sdf.ChangeBlock():
            for path,location in (('/World/Booster',p),('/World/Payload',stage_position)):
                prim=self.stage.GetPrimAtPath(path)
                prim.GetAttribute('xformOp:translate').Set(Gf.Vec3d(*location))
                prim.GetAttribute('xformOp:orient').Set(Gf.Quatf(float(q[0]),Gf.Vec3f(*q[1:])))
                rigid=UsdPhysics.RigidBodyAPI(prim)
                rigid.CreateVelocityAttr().Set(xyz(v));rigid.CreateAngularVelocityAttr().Set(Gf.Vec3f(0))
        for body,location in ((self.booster,p),(self.payload,stage_position)):
            body.set_default_state(positions=location[None,:],orientations=q[None,:],
                linear_velocities=v[None,:],angular_velocities=np.zeros((1,3)))
        self.world.reset()
        # Timeline reset restores Kit's simulation edit layer. Reauthor the
        # episode poses there before a new live constraint is registered.
        with Sdf.ChangeBlock():
            for path,location in (('/World/Booster',p),('/World/Payload',stage_position)):
                prim=self.stage.GetPrimAtPath(path)
                prim.GetAttribute('xformOp:translate').Set(Gf.Vec3d(*location))
                prim.GetAttribute('xformOp:orient').Set(Gf.Quatf(float(q[0]),Gf.Vec3f(*q[1:])))
                rigid=UsdPhysics.RigidBodyAPI(prim)
                rigid.CreateVelocityAttr().Set(xyz(v));rigid.CreateAngularVelocityAttr().Set(Gf.Vec3f(0))
        self.booster.set_world_poses(p[None,:],q[None,:]);self.booster.set_velocities(np.array([[*v,0.,0.,0.]],dtype=np.float32))
        self.payload.set_world_poses(stage_position[None,:],q[None,:]);self.payload.set_velocities(np.array([[*v,0.,0.,0.]],dtype=np.float32))
        self.payload.set_masses(np.array([max(1.,self.payload_mass)],dtype=np.float32))
        stage_inertia=np.array([self.payload_mass*(3*1.8**2+9**2)/12]*2+[self.payload_mass*1.8**2/2])
        self.payload.set_inertias(np.diag(stage_inertia).reshape(1,9).astype(np.float32))
        self.payload.set_visibilities(np.array([self.attached]))
        self.payload.enable_rigid_body_physics() if self.attached else self.payload.disable_rigid_body_physics()
        self._mass_update()
        self.stage_joint=self._joint('/World/PayloadConnector','/World/Booster','/World/Payload',[0,0,self.half],[0,0,-4.5])
        self.stage_joint.GetJointEnabledAttr().Set(self.attached)
        if self.on_pad:
            self.hold_joint=self._joint('/World/LaunchHoldDown',None,'/World/Booster',p,[0,0,0])
        self._sync()
        if self.visuals:self.visuals.update(self)
        return self.state()

    def _sync(self):
        poses,quaternions=self.booster.get_world_poses();velocities=self.booster.get_velocities()
        self.position=np.array(poses[0],dtype=float);self.quaternion=np.array(quaternions[0],dtype=float)
        self.velocity=np.array(velocities[0,:3],dtype=float);self.omega_world=np.array(velocities[0,3:],dtype=float)
        if not np.isfinite(np.r_[self.position,self.quaternion,self.velocity,self.omega_world]).all():raise FloatingPointError('PhysX returned nonfinite state')
        self._rotation=Rotation.from_quat([*self.quaternion[1:],self.quaternion[0]]).as_matrix()

    def rotation(self):return self._rotation
    def gravity(self,altitude=None):return gravity_at(self.w,self.position[2]-self.half if altitude is None else altitude)

    def set_landing_target(self,target):
        if self.visuals:self.visuals.set_landing_target(target)

    def set_roll_command(self,command):
        if not np.isfinite(command):raise ValueError('Nonfinite roll command')
        self.roll_command=float(np.clip(command,-1,1))

    def separate(self):
        if not self.attached:raise ValueError('Payload is already detached')
        if self.throttle>1e-8:raise ValueError('Engine must finish shutting down before payload release')
        event=dict(t=self.data.time,position=self.position.tolist(),velocity=self.velocity.tolist(),quaternion=self.quaternion.tolist(),mass=self.payload_mass)
        states=[]
        for path,body in (('/World/Booster',self.booster),('/World/Payload',self.payload)):
            position,quaternion=body.get_world_poses();states.append((path,position.copy(),quaternion.copy(),body.get_velocities()[0].copy()))
        # Commit removal before actor synchronization. Otherwise USD notices can
        # temporarily reconstruct the old joint against the newly authored poses.
        with Sdf.ChangeBlock():
            self.stage_joint.GetJointEnabledAttr().Set(False)
            self.stage_joint.GetCollisionEnabledAttr().Set(True)
        self.world.render()  # pumps USD/PhysX changes with playSimulations=false
        with Sdf.ChangeBlock():
            # PhysX can rebuild actors when the USD constraint topology changes.
            # Preserve their live states in USD, including angular velocity in
            # USD's degrees/second, so a rebuild cannot restore stale defaults.
            for path,position,quaternion,velocity in states:
                prim=self.stage.GetPrimAtPath(path)
                prim.GetAttribute('xformOp:translate').Set(Gf.Vec3d(*map(float,position[0])))
                prim.GetAttribute('xformOp:orient').Set(Gf.Quatf(float(quaternion[0,0]),xyz(quaternion[0,1:])))
                rigid=UsdPhysics.RigidBodyAPI(prim)
                rigid.CreateVelocityAttr().Set(xyz(velocity[:3]))
                rigid.CreateAngularVelocityAttr().Set(xyz(np.rad2deg(velocity[3:])))
        self.world.render()
        self.attached=False;self._mass_update()
        self.detached=True;self.separation_time=self.data.time;self.separation_axis=self.rotation()[:,2].copy()
        return event

    def state(self,include_payload=True):
        rotation=self.rotation();clearance,offset=contact_geometry(self.position,rotation,self.half,self.v.get('landing_foot_radius',6.2))
        contact_speed=np.linalg.norm(self.velocity+np.cross(self.omega_world,offset))
        stage=None
        if include_payload and getattr(self,'detached',False):
            p,q=self.payload.get_world_poses();velocity=self.payload.get_velocities()
            axis_z=abs(Rotation.from_quat([*q[0,1:],q[0,0]]).as_matrix()[2,2])
            extent=4.5*axis_z+1.8*np.sqrt(max(0.,1-axis_z**2))
            stage=dict(position=p[0].tolist(),quaternion=q[0].tolist(),velocity=velocity[0,:3].tolist(),impacted=bool(p[0,2]<=extent+.02))
        return dict(t=float(self.data.time),position=self.position.copy(),quaternion=self.quaternion.copy(),velocity=self.velocity.copy(),
            angular_velocity=rotation.T@self.omega_world,throttle=self.throttle,gimbal=self.gimbal.copy(),fuel_mass=float(self.fuel),mass=float(self.mass),
            wind=self.wind.copy(),tilt=float(np.rad2deg(np.arccos(np.clip(rotation[2,2],-1,1)))),altitude=float(self.position[2]-self.half),
            clearance=min(clearance,0.) if self._impacted else clearance,contact_speed=float(self._impact_speed if self._impacted else contact_speed),
            hold_down=self.on_pad,release_time=self.release_time,upper_stage=stage,
            rcs_fuel_mass=self.rcs.fuel,rcs_torque=self.rcs.torque,roll_rate=float((rotation.T@self.omega_world)[2]))

    def step(self,action,stop_on_impact=True):
        dt=self.w['timestep']
        for _ in range(self.w['control_substeps']):
            rotation=self.rotation();force,torque,burn=self.engine.step(action,dt,self.fuel,self.thrust_scale)
            torque[2]+=self.rcs.step(self.roll_command if not self.on_pad and not self._impacted else 0.,dt)
            self._mass_update()
            self.wind+=.3*(np.asarray(self.w['wind_mean'])*self.wind_scale-self.wind)*dt+self.rng.normal(0,self.w['gust_std']*self.wind_scale*np.sqrt(dt),3);self.wind[2]=0.
            relative=self.velocity-self.wind;rho=air_density(self.w,self.position[2]-self.half)
            drag=-.5*rho*self.v['drag_coefficient']*self.v['area']*np.linalg.norm(relative)*relative
            pusher=np.zeros(3);pusher_torque=np.zeros(3);payload_pusher_torque=np.zeros(3)
            if self.separation_time is not None:
                remaining=self.v.get('separation_pusher_seconds',.2)-(self.data.time-self.separation_time)
                if remaining>0:
                    payload_position,payload_q=self.payload.get_world_poses()
                    payload_rotation=Rotation.from_quat([*payload_q[0,1:],payload_q[0,0]]).as_matrix()
                    booster_pin=rotation@np.array([0.,0.,self.half]);payload_pin=payload_rotation@np.array([0.,0.,-4.5])
                    separation=payload_position[0]-self.position
                    axis=separation/np.linalg.norm(separation)
                    pusher=axis*self.v.get('separation_pusher_force',12000.)*np.clip(remaining/dt,0.,1.)
                    # The massless connector transmits equal/opposite forces
                    # through one interface, including the balancing moments.
                    # Using a near-zero pin gap as an axis amplifies GPU float
                    # roundoff just after release.
                    interface=.5*(self.position+booster_pin+payload_position[0]+payload_pin)
                    pusher_torque=np.cross(interface-self.position,-pusher)
                    payload_pusher_torque=np.cross(interface-payload_position[0],pusher)
            gravity=self.gravity()
            if abs(gravity-self._last_gravity)>1e-5:
                self.world.get_physics_context().set_gravity(-gravity);self._last_gravity=gravity
            if self.on_pad:
                ready=(rotation@force)[2]>=self.mass*self.gravity()*self.v.get('hold_down_release_margin',1.05)
                self.hold_elapsed=self.hold_elapsed+dt if ready else 0.
                if ready and self.hold_elapsed>=self.v.get('hold_down_release_time',.2):
                    self.hold_joint.GetJointEnabledAttr().Set(False);self.on_pad=False;self.release_time=float(self.data.time)
            self.booster.apply_forces_and_torques_at_pos(forces=(rotation@force+drag-pusher)[None,:].astype(np.float32),torques=(rotation@torque+pusher_torque)[None,:].astype(np.float32),is_global=True)
            if getattr(self,'detached',False):
                p,_=self.payload.get_world_poses();velocity=self.payload.get_velocities()[0,:3]-self.wind
                stage_drag=-.5*air_density(self.w,p[0,2])*self.v['drag_coefficient']*np.pi*1.8**2*np.linalg.norm(velocity)*velocity
                self.payload.apply_forces_and_torques_at_pos(forces=(stage_drag+pusher)[None,:].astype(np.float32),torques=payload_pusher_torque[None,:].astype(np.float32),is_global=True)
            before=self.state(include_payload=False);self.world.step(render=False);self.data.time+=dt;self.fuel=max(0.,self.fuel-burn);self._sync()
            state=self.state(include_payload=False)
            contact=state['clearance']<.1 and np.linalg.norm(self.booster.get_net_contact_forces(dt=dt)[0])>1e-3
            if state['clearance']>.1:self._contact_armed=True
            if not self.on_pad and self._contact_armed and ((contact and state['clearance']<.1) or state['clearance']<=0.):
                if not self._impacted:
                    self.impact_state=dict(t=self.data.time,position=before['position'].tolist(),velocity=before['velocity'].tolist(),
                        angular_velocity=before['angular_velocity'].tolist(),center_speed=float(np.linalg.norm(before['velocity'])),contact_speed=before['contact_speed'])
                self._impacted=True;self._impact_speed=max(before['contact_speed'],state['contact_speed'])
            self._render_step+=1
            if not self.headless and self._render_step%max(1,round(1/(30*dt)))==0:
                if self.visuals:self.visuals.update(self)
                self.world.render()
            if self._impacted and stop_on_impact:break
        return self.state()

    def close(self):
        self.world.stop()
