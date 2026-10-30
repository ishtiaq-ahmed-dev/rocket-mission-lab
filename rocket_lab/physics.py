"""Headless MuJoCo dynamics. SI units, world z up, quaternion w,x,y,z.

Variable mass is updated with mj_setConst as required by MuJoCo. Forces act
at the CoM and gimballed thrust adds the physical engine-lever torque.
Touchdown is detected before contact resolution, retaining impact velocity.
"""
import numpy as np
import mujoco
from .config import load_config
from .atmosphere import air_density

class RocketPhysics:
    def __init__(self, config=None):
        self.cfg = config or load_config()
        self.v = self.cfg["vehicle"]
        self.w = self.cfg["world"]
        self.half = self.v["length"] / 2
        # Top of the launch stand. Altitude is measured from it; `rest` is the body-centre height on it.
        self.stand = float(self.cfg["mission"].get("launch_stand_height", 0.))
        self.rest = self.half + self.stand
        self.engine_lever = self.v.get("engine_lever", self.half)
        mass = self.v["dry_mass"] + self.v["fuel_mass"]
        inertia = np.array(self.v["inertia"]) * mass / self.v["dry_mass"]
        xml = f'''<mujoco><option timestep="{self.w['timestep']}" gravity="0 0 -{self.w['gravity']}" integrator="RK4"/>
        <worldbody><body name="rocket" pos="0 0 {self.rest}"><freejoint/>
        <inertial pos="0 0 0" mass="{mass}" diaginertia="{' '.join(map(str,inertia))}"/>
        <geom type="cylinder" size="{self.v['radius']} {self.half}" contype="0" conaffinity="0"/>
        </body></worldbody></mujoco>'''
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        self.reset(0)

    def reset(self, seed, position=None, velocity=None, quaternion=None, mass_scale=1.0, wind_scale=1.0, thrust_scale=1.0):
        self.rng = np.random.default_rng(seed)
        self.mass_scale, self.wind_scale, self.thrust_scale = mass_scale, wind_scale, thrust_scale
        self.fuel = self.v["fuel_mass"] * mass_scale
        self.attached_mass = self.v.get('upper_stage_mass',0.) * mass_scale
        self.gimbal = np.zeros(2)
        self.rcs_torque = np.zeros(3)
        self.throttle = 0.0
        self.thrust = 0.0
        self.hold_elapsed = 0.0
        self.release_time = None
        self.released_stage = None
        self.wind = np.array(self.w["wind_mean"], dtype=float) * wind_scale
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:3] = position if position is not None else [0, 0, 200 + self.rest]
        self.data.qpos[3:7] = quaternion if quaternion is not None else [1, 0, 0, 0]
        self.data.qvel[:3] = velocity if velocity is not None else [0, 0, -20]
        # A vehicle standing on its pad is held by the legs/hold-downs until thrust exceeds weight.
        self.on_pad = bool(self.data.qpos[2] <= self.rest + 0.1 and np.linalg.norm(self.data.qvel[:3]) < 1e-6)
        if self.on_pad:
            self.data.qpos[2] = self.rest
            self.data.qpos[3:7] = [1, 0, 0, 0]
        self.pad_pose = self.data.qpos.copy()
        self._mass_update()
        mujoco.mj_forward(self.model, self.data)
        return self.state()

    @property
    def mass(self):
        return self.v["dry_mass"] * self.mass_scale + self.fuel + self.attached_mass

    def gravity(self, altitude=None):
        height=max(0.,float(self.data.qpos[2]-self.rest) if altitude is None else altitude)
        return gravity_at(self.w, height)

    def separate(self):
        """Release the upper stage with a spring-pusher impulse along the booster axis.

        The upper stage gains `separation_delta_v` m/s along the axis; momentum conservation
        gives the booster an equal and opposite kick scaled by the mass ratio. Both bodies
        then coast independently under gravity and drag. The booster stays under controller
        authority; the released stage is an unpowered ballistic body.
        """
        state=self.state()
        event=dict(t=state['t'],position=state['position'].tolist(),velocity=state['velocity'].tolist(),
                   quaternion=state['quaternion'].tolist(),mass=float(self.attached_mass))
        if self.attached_mass > 0:
            rotation = self.rotation()
            axis = rotation[:, 2]
            upper_mass = float(self.attached_mass)
            dv_upper = float(self.v.get('separation_delta_v', 1.3))
            impulse = upper_mass * dv_upper
            self.attached_mass = 0.
            self._mass_update()
            booster_mass = self.mass
            offset = rotation @ np.array([0., 0., self.half + 4.5])
            velocity = state['velocity'] + np.cross(rotation @ state['angular_velocity'], offset) + axis*dv_upper
            self.released_stage = BallisticStage(self.cfg, upper_mass,
                state['position'] + offset, velocity, state['quaternion'], state['angular_velocity'], state['t'])
            self.data.qvel[:3] = self.data.qvel[:3] - axis*impulse/booster_mass
        self.attached_mass=0.
        self._mass_update()
        return event

    def _mass_update(self):
        # mj_setConst uses qpos0 and overwrites data.qpos; preserve live state.
        qpos, qvel, clock = self.data.qpos.copy(), self.data.qvel.copy(), self.data.time
        self.model.body_mass[1] = self.mass
        self.model.body_inertia[1] = np.array(self.v["inertia"]) * self.mass / self.v["dry_mass"]
        mujoco.mj_setConst(self.model, self.data)
        self.data.qpos[:], self.data.qvel[:], self.data.time = qpos, qvel, clock

    def rotation(self):
        quaternion = self.data.qpos[3:7].copy()
        norm = mujoco.mju_normalize4(quaternion)
        if not 0 < norm < np.inf:
            raise ValueError("Quaternion must have finite nonzero norm")
        matrix = np.empty(9)
        mujoco.mju_quat2Mat(matrix, quaternion)
        return matrix.reshape(3, 3)

    def state(self):
        n = self.rotation()[:, 2]
        return dict(t=float(self.data.time), position=self.data.qpos[:3].copy(), quaternion=self.data.qpos[3:7].copy(),
                    velocity=self.data.qvel[:3].copy(), angular_velocity=self.data.qvel[3:6].copy(),
                    fuel_mass=float(self.fuel), mass=float(self.mass), wind=self.wind.copy(),
                    throttle=float(self.throttle), gimbal=self.gimbal.copy(),
                    altitude=float(self.data.qpos[2] - self.rest), tilt=float(np.degrees(np.arccos(np.clip(n[2], -1, 1)))),
                    clearance=self.contact_clearance(), contact_speed=self.contact_speed(),
                    hold_down=bool(self.on_pad), release_time=self.release_time,
                    upper_stage=self.released_stage.state() if self.released_stage else None)

    def feet(self):
        radius = self.v.get('landing_foot_radius', 6.2)
        angles = np.arange(4)*np.pi/2 + np.pi/4
        return np.column_stack([radius*np.cos(angles), radius*np.sin(angles), np.full(4, -self.half+.15)])

    def contact_clearance(self):
        if self.v.get('contact_model') != 'feet':
            return float(self.data.qpos[2]-self.rest)
        rotation = self.rotation()
        # Lowest point of each circular sole, including its radius and thickness.
        sole = .82*np.hypot(rotation[2, 0], rotation[2, 1]) + .15*abs(rotation[2, 2])
        return float(self.data.qpos[2] + np.min(self.feet() @ rotation[2]) - sole - self.stand)

    def contact_speed(self):
        rotation = self.rotation()
        feet = self.feet() @ rotation.T
        index = int(np.argmin(feet[:, 2]))
        return float(np.linalg.norm(self.data.qvel[:3] + np.cross(rotation @ self.data.qvel[3:6], feet[index])))

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=float), -1, 1)
        if action.shape != (3,) or not np.isfinite(action).all():
            raise ValueError("action must contain three finite normalized values")
        raw_throttle = (action[0] + 1) / 2
        commanded = 0 if raw_throttle < 0.02 or self.fuel <= 0 else max(self.v["min_throttle"], raw_throttle)
        limit = np.deg2rad(self.v["gimbal_limit_deg"])
        target_gimbal = action[1:] * limit
        dt = self.w["timestep"]
        rate_up = self.v.get("throttle_rate")
        rate_down = self.v.get("shutdown_rate", rate_up)
        for _ in range(self.w["control_substeps"]):
            self.gimbal += np.clip(target_gimbal - self.gimbal, -np.deg2rad(self.v["gimbal_rate_deg_s"])*dt, np.deg2rad(self.v["gimbal_rate_deg_s"])*dt)
            if rate_up and self.fuel > 0:
                # Turbopump/valve spool: thrust follows the command at a bounded rate, so ignition
                # and shutdown ramp over a few tenths of a second instead of stepping instantly.
                delta = commanded - self.throttle
                self.throttle += np.clip(delta, -rate_down*dt, rate_up*dt)
                self.thrust = self.throttle * self.v["max_thrust"] * self.thrust_scale
            else:
                self.thrust = commanded * self.v["max_thrust"] * self.thrust_scale if self.fuel > 0 else 0
            # F = mdot * Isp * g0. Cap the final substep to available fuel.
            self.thrust = min(self.thrust, self.fuel * self.v["isp"] * self.w["gravity"] / dt)
            self.throttle = self.thrust / (self.v["max_thrust"] * self.thrust_scale) if self.thrust_scale > 0 else 0
            self._mass_update()
            rotation = self.rotation()
            direction = np.array([np.tan(self.gimbal[0]), np.tan(self.gimbal[1]), 1.0])
            force_body = direction / np.linalg.norm(direction) * self.thrust
            force_world = rotation @ force_body
            torque_body = np.array([self.engine_lever*force_body[1], -self.engine_lever*force_body[0], 0.])
            # OU gusts are generated once per integration step from the seeded RNG.
            self.wind += 0.3 * (np.array(self.w["wind_mean"])*self.wind_scale - self.wind)*dt + self.rng.normal(0, self.w["gust_std"]*self.wind_scale*np.sqrt(dt), 3)
            self.wind[2] = 0
            relative = self.data.qvel[:3] - self.wind
            rho = air_density(self.w,self.data.qpos[2]-self.rest)
            drag = -0.5*rho*self.v["drag_coefficient"]*self.v["area"]*np.linalg.norm(relative)*relative
            self.data.qfrc_applied[:3] = force_world + drag
            # Free-joint rotational generalized forces use the local tangent
            # frame. Holding a world torque constant through RK4's stages
            # creates a spurious roll moment as the body rotates within dt.
            # Cold-gas RCS: bounded body torque, used only by the controller during the coast.
            limit_rcs = self.v.get('rcs_torque_max', 0.)
            rcs = np.clip(self.rcs_torque, -limit_rcs, limit_rcs)
            self.data.qfrc_applied[3:6] = torque_body + rcs
            self.model.opt.gravity[2] = -self.gravity()
            before_pos, before_vel, before_time = self.data.qpos.copy(), self.data.qvel.copy(), self.data.time
            before_clearance = self.contact_clearance()
            if self.on_pad:
                ready = force_world[2] >= self.mass*self.w['gravity']*self.v.get('hold_down_release_margin', 1.)
                self.hold_elapsed = self.hold_elapsed + dt if ready else 0.
                if ready and self.hold_elapsed + 1e-9 >= self.v.get('hold_down_release_time', 0.):
                    self.on_pad = False
                    self.release_time = float(self.data.time)
            mujoco.mj_step(self.model, self.data)
            self.fuel = max(0., self.fuel - self.thrust*dt/(self.v["isp"]*self.w["gravity"]))
            if self.on_pad:
                # A constrained launch support carries the reaction load while
                # thrust builds. It releases once, never reattaches in flight.
                self.data.qpos[:] = self.pad_pose
                self.data.qvel[:] = 0.
            elif self.contact_clearance() <= 0:
                if before_clearance > 0:
                    # Locate first sole contact within this integration substep.
                    # Interpolate only to the impact instant, retaining lateral
                    # position and velocity; no landing-coordinate correction.
                    after_pos, after_vel = self.data.qpos.copy(), self.data.qvel.copy()
                    lower, upper = 0., 1.
                    for _ in range(24):
                        fraction = (lower+upper)/2
                        self.data.qpos[:] = before_pos + fraction*(after_pos-before_pos)
                        mujoco.mju_normalize4(self.data.qpos[3:7])
                        if self.contact_clearance() > 0: lower = fraction
                        else: upper = fraction
                    self.data.qvel[:] = before_vel + upper*(after_vel-before_vel)
                    self.data.time = before_time + upper*dt
                    self.fuel += self.thrust*dt*(1-upper)/(self.v['isp']*self.w['gravity'])
                break
        if self.released_stage:
            self.released_stage.advance(float(self.data.time))
        return self.state()


class BallisticStage:
    """Independent unpowered free body integrated by MuJoCo after release.

    This generic stage has drag and gravity but no propulsion or guidance.
    It is recorded on the physics clock, never extrapolated by the renderer.
    """
    def __init__(self, cfg, mass, position, velocity, quaternion, angular_velocity, clock):
        self.cfg, self.mass = cfg, mass
        inertia = [mass*(3*1.8**2+9**2)/12]*2 + [mass*1.8**2/2]
        self.model = mujoco.MjModel.from_xml_string(f'''<mujoco><option timestep="{cfg['world']['timestep']}" gravity="0 0 -{cfg['world']['gravity']}" integrator="RK4"/>
        <worldbody><body><freejoint/><inertial pos="0 0 0" mass="{mass}" diaginertia="{' '.join(map(str,inertia))}"/>
        <geom type="cylinder" size="1.8 4.5" contype="0" conaffinity="0"/></body></worldbody></mujoco>''')
        self.data = mujoco.MjData(self.model)
        self.data.qpos[:] = [*position, *quaternion]
        self.data.qvel[:] = [*velocity, *angular_velocity]
        self.data.time = clock
        self.impacted = False
        mujoco.mj_forward(self.model, self.data)

    def advance(self, clock):
        nominal = self.cfg['world']['timestep']
        while self.data.time < clock-1e-8 and not self.impacted:
            self.model.opt.timestep = min(nominal, clock-self.data.time)
            relative = self.data.qvel[:3]-np.asarray(self.cfg['world']['wind_mean'])
            rho = air_density(self.cfg['world'],self.data.qpos[2])
            self.model.opt.gravity[2] = -gravity_at(self.cfg['world'], self.data.qpos[2])
            self.data.xfrc_applied[1, :3] = -.5*rho*.5*10.18*np.linalg.norm(relative)*relative
            mujoco.mj_step(self.model, self.data)
            if self.data.qpos[2] <= 4.5: self.impacted = True

    def state(self):
        return dict(position=self.data.qpos[:3].tolist(), velocity=self.data.qvel[:3].tolist(),
                    quaternion=self.data.qpos[3:7].tolist(), impacted=self.impacted)


def gravity_at(world, altitude):
    """Local vertical inverse-square gravity for the suborbital study.

    The flat local-coordinate model omits Earth rotation and downrange curvature.
    Isp fuel flow always uses the constant surface reference g0 instead.
    """
    if world.get('gravity_model')=='inverse_square':
        radius=world.get('earth_radius',6371000.)
        return world['gravity']*(radius/(radius+max(0.,altitude)))**2
    return world['gravity']
