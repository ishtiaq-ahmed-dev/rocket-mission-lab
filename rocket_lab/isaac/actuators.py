"""Engine units/actions shared with the existing 21-state policy contract."""
import numpy as np


class Engine:
    def __init__(self,vehicle,g0):
        self.vehicle=vehicle;self.g0=g0;self.reset()

    def reset(self):
        self.throttle=0.;self.gimbal=np.zeros(2);self.thrust=0.

    def step(self,action,dt,fuel,thrust_scale=1.):
        action=np.asarray(action,dtype=float)
        if action.shape!=(3,) or not np.isfinite(action).all():raise ValueError('Expected three finite control actions')
        action=np.clip(action,-1,1);v=self.vehicle
        demand=(action[0]+1)*.5
        commanded=0. if demand<.02 or fuel<=0 else max(v['min_throttle'],demand)
        target=action[1:]*np.deg2rad(v['gimbal_limit_deg'])
        rate=np.deg2rad(v['gimbal_rate_deg_s'])*dt
        self.gimbal+=np.clip(target-self.gimbal,-rate,rate)
        rise=v.get('throttle_rate',0.)
        if rise:self.throttle+=np.clip(commanded-self.throttle,-v.get('shutdown_rate',rise)*dt,rise*dt)
        else:self.throttle=commanded
        available=max(0.,fuel)*v['isp']*self.g0/dt
        self.thrust=min(self.throttle*v['max_thrust']*thrust_scale,available)
        self.throttle=float(self.thrust/(v['max_thrust']*thrust_scale)) if thrust_scale>0 else 0.
        direction=np.array([np.tan(self.gimbal[0]),np.tan(self.gimbal[1]),1.])
        body_force=direction/np.linalg.norm(direction)*self.thrust
        lever=v.get('engine_lever',v['length']/2)
        torque=np.array([lever*body_force[1],-lever*body_force[0],0.])
        return body_force,torque,self.thrust*dt/(v['isp']*self.g0)


class RollThrusters:
    """Two opposed tangential jets: zero net force, bounded roll moment and gas."""
    def __init__(self,vehicle):
        self.vehicle=vehicle;self.reset()

    def reset(self):
        self.fuel=float(self.vehicle.get('rcs_fuel_mass',0.));self.torque=0.

    def step(self,command,dt):
        if not np.isfinite(command) or dt<=0:raise ValueError('Invalid roll command or timestep')
        radius=self.vehicle.get('rcs_lever',1.8);isp=self.vehicle.get('rcs_isp',60.)
        limit=2*radius*self.vehicle.get('rcs_jet_force',500.)
        requested=float(np.clip(command,-1,1))*limit
        burn=abs(requested)/radius*dt/(isp*9.80665)
        fraction=min(1.,self.fuel/max(burn,1e-15))
        self.torque=requested*fraction;self.fuel=max(0.,self.fuel-burn*fraction)
        return self.torque


def gravity_at(world,altitude):
    radius=world.get('earth_radius',6371000.)
    return world['gravity']*(radius/(radius+max(0.,altitude)))**2 if world.get('gravity_model')=='inverse_square' else world['gravity']


def contact_geometry(position,rotation,half,radius=6.2):
    feet=np.array([[radius,0,-half+.15],[-radius,0,-half+.15],[0,radius,-half+.15],[0,-radius,-half+.15]])
    offsets=feet@rotation.T
    index=int(np.argmin(offsets[:,2]))
    return float(position[2]+offsets[index,2]-.15),offsets[index]
