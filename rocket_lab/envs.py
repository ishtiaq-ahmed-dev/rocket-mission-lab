import gymnasium as gym
from gymnasium import spaces
import numpy as np
from scipy.spatial.transform import Rotation
from .physics import RocketPhysics
from .config import load_config

class RocketEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, mission="landing", config=None, difficulty=1.0, randomize=True, noise=True):
        super().__init__()
        self.cfg = config or load_config()
        self.mission = mission
        self.difficulty = difficulty
        self.randomize, self.noise = randomize, noise
        self.physics = RocketPhysics(self.cfg)
        self.action_space = spaces.Box(-1., 1., (3,), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf, (21,), dtype=np.float32)
        self.phase = mission

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        rng, m, d = self.np_random, self.cfg["mission"], self.difficulty
        self.phase = "takeoff" if self.mission in ("takeoff", "combined") else "landing"
        self.separated = False
        if self.phase == "landing":
            h = rng.uniform(*m["landing_altitude"]) * (0.25 + 0.75*d)
            pos = [*rng.uniform(-m["horizontal_position"]*d, m["horizontal_position"]*d, 2), h+self.physics.half]
            vel = [*rng.uniform(-m["horizontal_velocity"]*d, m["horizontal_velocity"]*d, 2), rng.uniform(*m["landing_vertical_velocity"])*(0.3+0.7*d)]
        else:
            pos, vel = [0, 0, self.physics.half+0.05], [0, 0, 0]
        q = Rotation.from_euler("xy", rng.uniform(-m["initial_tilt_deg"]*d, m["initial_tilt_deg"]*d, 2), degrees=True).as_quat()
        mass_scale = rng.uniform(0.95, 1.05) if self.randomize else 1.0
        thrust_scale = rng.uniform(0.97, 1.03) if self.randomize else 1.0
        self.physics.reset(int(rng.integers(0, 2**31)), pos, vel, [q[3], *q[:3]], mass_scale, d if self.randomize else 0., thrust_scale)
        if options:
            if "state" in options:
                p = self.physics
                p.reset(seed or 0, **options["state"])
        self.last_state = self.physics.state()
        self.previous_potential = self._potential(self.last_state)
        self.total_reward = 0.
        self.last_info = {}
        return self._obs(self.last_state), {}

    def _target(self):
        return np.array([*self.cfg["mission"]["pad"][:2], self.physics.half + (self.cfg["mission"]["takeoff_altitude"] if self.phase == "takeoff" else 0.)])

    def _obs(self, s):
        # Only physical state, clock and relative goal. No controller/expert action.
        obs = np.concatenate([np.asarray(s["position"])/400, np.asarray(s["velocity"])/50,
                              s["quaternion"], np.asarray(s["angular_velocity"])/2,
                              [s["fuel_mass"] / (self.cfg["vehicle"]["fuel_mass"]*self.physics.mass_scale), s["t"]/90],
                              (self._target()-s["position"])/400,
                              [self.cfg["mission"]["takeoff_velocity"]/50 if self.phase=="takeoff" else 0, s["mass"]/40000, s["throttle"]]])
        if self.noise:
            noise = self.np_random.normal(0, self.cfg["world"]["sensor_noise"]*self.difficulty, obs.shape)
            noise[6:10] = 0 # do not corrupt quaternion representation
            obs += noise
        return obs.astype(np.float32)

    def _potential(self, s):
        return -np.linalg.norm(self._target()-s["position"])

    def step(self, action):
        old = self.last_state
        s = self.physics.step(action)
        m, r = self.cfg["mission"], self.cfg["reward"]
        speed = float(np.linalg.norm(s["velocity"]))
        distance = float(np.linalg.norm(s["position"][:2]-np.array(m["pad"][:2])))
        reason = None
        phase_changed = False
        if self.phase == "takeoff" and s["altitude"] >= m["takeoff_altitude"]:
            if abs(s["velocity"][2]-m["takeoff_velocity"]) > m["takeoff_velocity_tolerance"]:
                reason = "crash_speed"
            elif s["tilt"] >= m["touchdown_tilt_deg"]:
                reason = "crash_tilt"
            elif distance > m["pad_radius"]:
                reason = "missed_pad"
            elif self.mission == "combined":
                self.phase, self.separated, phase_changed = "landing", True, True
            else:
                reason = "success"
        if s["altitude"] <= 0 and reason is None:
            if self.phase == "takeoff":
                reason = "crash_speed"
            elif speed >= m["touchdown_speed"]:
                reason = "crash_speed"
            elif s["tilt"] >= m["touchdown_tilt_deg"]:
                reason = "crash_tilt"
            elif distance > m["pad_radius"]:
                reason = "missed_pad"
            else:
                reason = "success"
        if reason is None and s["fuel_mass"] <= 0:
            reason = "out_of_fuel"
        if reason is None and (np.linalg.norm(s["position"][:2]) > m["bounds"] or s["altitude"] > m["bounds"]):
            reason = "out_of_bounds"
        if reason is None and s["t"] >= m["timeout"]:
            reason = "timeout"
        potential = self._potential(s)
        progress = 0. if phase_changed else potential-self.previous_potential
        vertical_error = s["velocity"][2]-m["takeoff_velocity"] if self.phase=="takeoff" else speed*max(0.1, 1-min(s["altitude"]/100, 1))
        dt = s["t"]-old["t"]
        reward = r["progress"]*progress - dt*(r["velocity"]*vertical_error**2 + r["tilt"]*np.deg2rad(s["tilt"])**2 + r["angular_velocity"]*np.linalg.norm(s["angular_velocity"])**2 + r["position"]*distance + r["alive"]) - r["fuel"]*(old["fuel_mass"]-s["fuel_mass"])
        if reason:
            reward += r["success"] if reason=="success" else r["failure"]
        self.total_reward += reward
        self.previous_potential, self.last_state = potential, s
        info = dict(outcome=reason, failure_reason=None if reason in (None,"success") else reason,
                    touchdown_speed=speed, tilt=s["tilt"], pad_distance=distance,
                    fuel_used=self.cfg["vehicle"]["fuel_mass"]*self.physics.mass_scale-s["fuel_mass"], phase=self.phase)
        self.last_info = info
        return self._obs(s), float(reward), reason is not None and reason!="timeout", reason=="timeout", info

class LandingEnv(RocketEnv):
    def __init__(self, **kwargs): super().__init__("landing", **kwargs)

class TakeoffEnv(RocketEnv):
    def __init__(self, **kwargs): super().__init__("takeoff", **kwargs)
