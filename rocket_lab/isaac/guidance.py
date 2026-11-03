"""Native guidance model: compound-body inertia and measured engine identification.

Only the controller's prediction model changes. The native engine/rigid bodies
retain their configured physical parameters throughout a flight.
"""
from types import SimpleNamespace
import numpy as np
from ..controllers import ClassicalController
from ..atmosphere import aerodynamic_force
from ..propulsion import engine_performance


class View:
    def __init__(self,real,**values):self.real=real;self.__dict__.update(values)
    def __getattr__(self,name):return getattr(self.real,name)


class NativeGuidance(ClassicalController):
    def __init__(self):
        super().__init__(4);self.engine_scale=1.;self.identification_previous=None;self.previous_attachment=None
        self.reference_acceleration=1.;self.reference_braking=1.5;self.reference_velocity=None
        # Long-range plans must honor the native engine/body slew governor.
        # The legacy 45 m/s reference outruns it, overshoots, then spends the
        # landing reserve on repeated diverts. No physical actuator is scaled.
        self.transfer_cruise_speed=25.;self.transfer_brake_decel=1.0;self.transfer_shelf_limit=400.
        # Lower descent energy before the engine-floor pulse regime. PhysX
        # includes first-foot contact and valve lag, so a gentler terminal
        # profile leaves margin under the unchanged 2 m/s contact-speed gate.
        self.terminal_braking=1.5;self.touchdown_floor=.8

    def on_retarget(self):
        super().on_retarget();self.terminal_captured=False;self.reference_velocity=None

    def identify(self,env,s):
        previous=self.identification_previous;self.identification_previous=s
        if previous is None:return
        dt=s['t']-previous['t'];throttle=.5*(s['throttle']+previous['throttle'])
        if not 0<dt<.25 or throttle<.25 or abs(s['throttle']-previous['throttle'])>.02 or s['hold_down'] or s['clearance']<5:return
        ph=env.physics;gimbal=.5*(np.asarray(s['gimbal'])+previous['gimbal'])
        direction=np.array([np.tan(gimbal[0]),np.tan(gimbal[1]),1.]);direction/=np.linalg.norm(direction);axis=ph.rotation()@direction
        velocity=.5*(np.asarray(s['velocity'])+previous['velocity'])
        drag=aerodynamic_force(ph.w,ph.v,ph.rotation(),velocity,s['wind'],s['position'][2]-ph.rest)
        observed=(np.asarray(s['velocity'])-previous['velocity'])/dt+np.array([0.,0.,ph.gravity()])-drag/s['mass']
        expected=engine_performance(ph.w,ph.v,throttle,s['position'][2]-ph.rest)[0]
        estimate=float(np.dot(observed,axis)/(expected/s['mass'])) if expected>0 else 1.
        if .8<estimate<1.2:self.engine_scale+=(1-np.exp(-dt/3.))*(estimate-self.engine_scale)

    def action(self,env):
        ph=env.physics;s=getattr(env,'sensed_state',ph.state());self.identify(env,s)
        # Perfect-state runs already supply the actual native velocity and
        # gyro. A model-aided sensor filter adds pulse-valve integration error
        # and lag to these exact measurements. Retain it for noisy navigation.
        if not getattr(env,'noise',False):self.estimate=None
        if self.previous_attachment is not None and ph.attached!=self.previous_attachment:self.lqr_gain=None
        self.previous_attachment=ph.attached
        if self.terminal_captured and s['altitude']>5 and (np.linalg.norm(s['position'][:2]-env.landing)>1 or np.linalg.norm(s['velocity'][:2])>.5):
            self.terminal_captured=False
        vehicle={**ph.v,'max_thrust':ph.v['max_thrust']*self.engine_scale}
        for key in ('thrust_vacuum','thrust_sea_level'):
            if key in vehicle:vehicle[key]*=self.engine_scale
        inertia=ph.model.body_inertia.copy();lever=ph.engine_lever
        if ph.attached:
            booster_mass=s['mass']-ph.payload_mass;distance=ph.half+4.5
            reduced_mass=booster_mass*ph.payload_mass/s['mass']
            inertia[1,:2]+=ph.payload_mass*(3*1.8**2+9**2)/12+reduced_mass*distance**2
            inertia[1,2]+=ph.payload_mass*1.8**2/2
            lever+=ph.payload_mass*distance/s['mass']
        landing=getattr(env,'phase',None)=='landing'
        # Launch supports raise the held stack, not the remote landing surface.
        # Use the foot-contact body height for descent, retaining launch rest
        # height for ascent. This changes the prediction model, never a pose.
        rest=ph.half if landing else getattr(ph,'rest',ph.half)
        # A high-altitude retarget already has the normal transfer shelf below
        # it. Keeping the emergency -1 m/s divert descent there wastes the
        # landing reserve throughout the entire kilometre-long transfer.
        if landing and self.divert and s['position'][2]-rest>=self.transfer_shelf_limit:
            self.divert=False
        sensed={**s,'altitude':s['position'][2]-rest} if landing else s
        model=View(ph,v=vehicle,rest=rest,engine_lever=lever,model=SimpleNamespace(body_inertia=inertia))
        if hasattr(ph,'set_roll_command'):
            maximum=2*ph.v.get('rcs_lever',1.8)*ph.v.get('rcs_jet_force',500.)
            ph.set_roll_command(-s['angular_velocity'][2]*inertia[1,2]/(2.*maximum))
        return super().action(View(env,physics=model,sensed_state=sensed))
