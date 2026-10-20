"""Headless MuJoCo dynamics. SI units, world z up, quaternion w,x,y,z.

Variable mass is updated with mj_setConst as required by MuJoCo. Forces act
at the CoM and gimballed thrust adds the physical engine-lever torque.
Touchdown is detected before contact resolution, retaining impact velocity.
"""
import numpy as np
import mujoco
from .config import load_config

class RocketPhysics:
    def __init__(self, config=None):
        self.cfg = config or load_config()
        self.v = self.cfg["vehicle"]
        self.w = self.cfg["world"]
        self.half = self.v["length"] / 2
        mass = self.v["dry_mass"] + self.v["fuel_mass"]
        inertia = np.array(self.v["inertia"]) * mass / self.v["dry_mass"]
        xml = f'''<mujoco><option timestep="{self.w['timestep']}" gravity="0 0 -{self.w['gravity']}" integrator="RK4"/>
        <worldbody><body name="rocket" pos="0 0 {self.half}"><freejoint/>
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
        self.gimbal = np.zeros(2)
        self.throttle = 0.0
        self.thrust = 0.0
        self.wind = np.array(self.w["wind_mean"], dtype=float) * wind_scale
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:3] = position if position is not None else [0, 0, 200 + self.half]
        self.data.qpos[3:7] = quaternion if quaternion is not None else [1, 0, 0, 0]
        self.data.qvel[:3] = velocity if velocity is not None else [0, 0, -20]
        self._mass_update()
        mujoco.mj_forward(self.model, self.data)
        return self.state()

    @property
    def mass(self):
        return self.v["dry_mass"] * self.mass_scale + self.fuel

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
                    altitude=float(self.data.qpos[2] - self.half), tilt=float(np.degrees(np.arccos(np.clip(n[2], -1, 1)))))

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=float), -1, 1)
        if action.shape != (3,) or not np.isfinite(action).all():
            raise ValueError("action must contain three finite normalized values")
        raw_throttle = (action[0] + 1) / 2
        commanded = 0 if raw_throttle < 0.02 or self.fuel <= 0 else max(self.v["min_throttle"], raw_throttle)
        limit = np.deg2rad(self.v["gimbal_limit_deg"])
        target_gimbal = action[1:] * limit
        dt = self.w["timestep"]
        for _ in range(self.w["control_substeps"]):
            self.gimbal += np.clip(target_gimbal - self.gimbal, -np.deg2rad(self.v["gimbal_rate_deg_s"])*dt, np.deg2rad(self.v["gimbal_rate_deg_s"])*dt)
            self.thrust = commanded * self.v["max_thrust"] * self.thrust_scale if self.fuel > 0 else 0
            # F = mdot * Isp * g0. Cap the final substep to available fuel.
            self.thrust = min(self.thrust, self.fuel * self.v["isp"] * self.w["gravity"] / dt)
            self.throttle = self.thrust / (self.v["max_thrust"] * self.thrust_scale) if self.thrust_scale > 0 else 0
            self._mass_update()
            rotation = self.rotation()
            direction = np.array([np.tan(self.gimbal[0]), np.tan(self.gimbal[1]), 1.0])
            force_body = direction / np.linalg.norm(direction) * self.thrust
            force_world = rotation @ force_body
            torque_world = rotation @ np.array([self.half*force_body[1], -self.half*force_body[0], 0.])
            # OU gusts are generated once per integration step from the seeded RNG.
            self.wind += 0.3 * (np.array(self.w["wind_mean"])*self.wind_scale - self.wind)*dt + self.rng.normal(0, self.w["gust_std"]*self.wind_scale*np.sqrt(dt), 3)
            self.wind[2] = 0
            relative = self.data.qvel[:3] - self.wind
            rho = self.w["density_sea_level"] * np.exp(-max(0, self.data.qpos[2]-self.half)/self.w["scale_height"])
            drag = -0.5*rho*self.v["drag_coefficient"]*self.v["area"]*np.linalg.norm(relative)*relative
            self.data.xfrc_applied[1, :3] = force_world + drag
            self.data.xfrc_applied[1, 3:] = torque_world
            mujoco.mj_step(self.model, self.data)
            self.fuel = max(0., self.fuel - self.thrust*dt/(self.v["isp"]*self.w["gravity"]))
            if self.data.qpos[2] <= self.half:
                break
        return self.state()
