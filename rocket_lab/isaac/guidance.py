"""Native guidance model: compound-body inertia and measured engine identification.

Only the controller's prediction model changes. The native engine/rigid bodies
retain their configured physical parameters throughout a flight.
"""
from types import SimpleNamespace
import numpy as np
from ..controllers import ClassicalController
from ..atmosphere import air_density


class View:
    def __init__(self,real,**values):self.real=real;self.__dict__.update(values)
    def __getattr__(self,name):return getattr(self.real,name)


class NativeGuidance(ClassicalController):
    def __init__(self):
        super().__init__(4);self.engine_scale=1.;self.identification_previous=None;self.previous_attachment=None
        self.reference_acceleration=1.;self.reference_braking=1.5;self.reference_velocity=None

    def on_retarget(self):
        super().on_retarget();self.terminal_captured=False;self.reference_velocity=None

    def identify(self,env,s):
        previous=self.identification_previous;self.identification_previous=s
        if previous is None:return
        dt=s['t']-previous['t'];throttle=.5*(s['throttle']+previous['throttle'])
        if not 0<dt<.25 or throttle<.25 or abs(s['throttle']-previous['throttle'])>.02 or s['hold_down'] or s['clearance']<5:return
        ph=env.physics;gimbal=.5*(np.asarray(s['gimbal'])+previous['gimbal'])
        direction=np.array([np.tan(gimbal[0]),np.tan(gimbal[1]),1.]);direction/=np.linalg.norm(direction);axis=ph.rotation()@direction
        velocity=.5*(np.asarray(s['velocity'])+previous['velocity']);relative=velocity-s['wind']
        drag=-.5*air_density(ph.w,s['position'][2]-ph.half)*ph.v['drag_coefficient']*ph.v['area']*np.linalg.norm(relative)*relative
        observed=(np.asarray(s['velocity'])-previous['velocity'])/dt+np.array([0.,0.,ph.gravity()])-drag/s['mass']
        estimate=float(np.dot(observed,axis)/(throttle*ph.v['max_thrust']/s['mass']))
        if .8<estimate<1.2:self.engine_scale+=(1-np.exp(-dt/3.))*(estimate-self.engine_scale)

    def action(self,env):
        ph=env.physics;s=getattr(env,'sensed_state',ph.state());self.identify(env,s)
        if self.previous_attachment is not None and ph.attached!=self.previous_attachment:self.lqr_gain=None
        self.previous_attachment=ph.attached
        if self.terminal_captured and s['altitude']>5 and (np.linalg.norm(s['position'][:2]-env.landing)>1 or np.linalg.norm(s['velocity'][:2])>.5):
            self.terminal_captured=False
        vehicle={**ph.v,'max_thrust':ph.v['max_thrust']*self.engine_scale}
        inertia=ph.model.body_inertia.copy();lever=ph.engine_lever
        if ph.attached:
            booster_mass=s['mass']-ph.payload_mass;distance=ph.half+4.5
            reduced_mass=booster_mass*ph.payload_mass/s['mass']
            inertia[1,:2]+=ph.payload_mass*(3*1.8**2+9**2)/12+reduced_mass*distance**2
            inertia[1,2]+=ph.payload_mass*1.8**2/2
            lever+=ph.payload_mass*distance/s['mass']
        model=View(ph,v=vehicle,engine_lever=lever,model=SimpleNamespace(body_inertia=inertia))
        if hasattr(ph,'set_roll_command'):
            maximum=2*ph.v.get('rcs_lever',1.8)*ph.v.get('rcs_jet_force',500.)
            ph.set_roll_command(-s['angular_velocity'][2]*inertia[1,2]/(2.*maximum))
        return super().action(View(env,physics=model))
