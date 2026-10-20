import gymnasium as gym
from gymnasium import spaces
import numpy as np
from scipy.spatial.transform import Rotation
from .physics import RocketPhysics
from .config import load_config

class RocketEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, mission="landing", config=None, difficulty=1.0, randomize=True, noise=True, training=False):
        super().__init__()
        self.cfg = config or load_config()
        self.mission = mission
        self.difficulty = difficulty
        self.episode_difficulty = difficulty
        self.training = training
        self.takeoff_altitude=self.cfg["mission"]["takeoff_altitude"]
        self.takeoff_velocity=self.cfg["mission"]["takeoff_velocity"]
        probability=self.cfg["training"].get("full_start_probability",0.)
        if not 0<=probability<=1:raise ValueError("full_start_probability must be within [0,1]")
        self.randomize, self.noise = randomize, noise
        self.physics = RocketPhysics(self.cfg)
        self.action_space = spaces.Box(-1., 1., (3,), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf, (21,), dtype=np.float32)
        self.phase = mission

    def set_difficulty(self, value):
        if not 0<=value<=1:raise ValueError("difficulty must be within [0,1]")
        self.difficulty=float(value)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        rng, m, d = self.np_random, self.cfg["mission"], self.difficulty
        probability=self.cfg["training"].get("full_start_probability",0.)
        # Training-only distribution mixing; evaluation always uses the exact
        # requested difficulty. Skip the RNG draw when disabled to preserve seeds.
        if self.training and self.mission=="landing" and probability>0 and rng.random()<probability:d=1.
        self.episode_difficulty=d
        self.takeoff_altitude=m["takeoff_altitude"];self.takeoff_velocity=m["takeoff_velocity"]
        settings=self.cfg["training"]
        if self.training and self.mission=="takeoff" and settings.get("takeoff_goal_curriculum",False):
            start_height=settings["takeoff_curriculum_altitude"]
            start_velocity=settings["takeoff_curriculum_velocity"]
            if not 0<start_height<=m["takeoff_altitude"] or not 0<start_velocity<=m["takeoff_velocity"]:
                raise ValueError("Takeoff curriculum goals must be positive and within the full mission")
            self.takeoff_altitude=start_height+d*(m["takeoff_altitude"]-start_height)
            self.takeoff_velocity=start_velocity+d*(m["takeoff_velocity"]-start_velocity)
        self.phase = "takeoff" if self.mission in ("takeoff", "combined") else "landing"
        self.separated = False
        if self.phase == "landing":
            # The first curriculum stage is genuinely easy: 3 m, -0.8 m/s,
            # centered and upright. d=1 preserves the complete mission ranges.
            h = 3. + d*(rng.uniform(*m["landing_altitude"])-3.)
            pos = [*rng.uniform(-m["horizontal_position"]*d, m["horizontal_position"]*d, 2), h+self.physics.half]
            vel = [*rng.uniform(-m["horizontal_velocity"]*d, m["horizontal_velocity"]*d, 2), -.8+d*(rng.uniform(*m["landing_vertical_velocity"])+.8)]
        else:
            pos, vel = [0, 0, self.physics.half+0.05], [0, 0, 0]
        q = Rotation.from_euler("xy", rng.uniform(-m["initial_tilt_deg"]*d, m["initial_tilt_deg"]*d, 2), degrees=True).as_quat()
        mass_scale = rng.uniform(1-.05*d, 1+.05*d) if self.randomize else 1.0
        thrust_scale = rng.uniform(1-.03*d, 1+.03*d) if self.randomize else 1.0
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
        return np.array([*self.cfg["mission"]["pad"][:2], self.physics.half + (self.takeoff_altitude if self.phase == "takeoff" else 0.)])

    def _obs(self, s):
        # Only physical state, clock and relative goal. No controller/expert action.
        train=self.cfg["training"]
        position_scale=np.asarray(train.get("observation_position_scale",[400,400,400]))
        velocity_scale=np.asarray(train.get("observation_velocity_scale",[50,50,50]))
        obs = np.concatenate([np.asarray(s["position"])/position_scale, np.asarray(s["velocity"])/velocity_scale,
                              s["quaternion"], np.asarray(s["angular_velocity"])/2,
                              [s["fuel_mass"] / (self.cfg["vehicle"]["fuel_mass"]*self.physics.mass_scale), s["t"]/90],
                              (self._target()-s["position"])/position_scale,
                              [self.takeoff_velocity/50 if self.phase=="takeoff" else 0, s["mass"]/40000, s["throttle"]]])
        if self.noise:
            noise = self.np_random.normal(0, self.cfg["world"]["sensor_noise"]*self.episode_difficulty, obs.shape)
            noise[6:10] = 0 # do not corrupt quaternion representation
            obs += noise
        # Sensor magnitudes remain identical for both methods across changes to
        # the neural-network feature scale. Noise is defined in legacy SI scale.
        if self.noise:
            obs[:3]-=noise[:3];obs[:3]+=noise[:3]*400/position_scale
            obs[3:6]-=noise[3:6];obs[3:6]+=noise[3:6]*50/velocity_scale
        self.sensed_state={**s,"position":obs[:3]*position_scale,"velocity":obs[3:6]*velocity_scale,"angular_velocity":obs[10:13]*2}
        return obs.astype(np.float32)

    def _potential(self, s):
        r=self.cfg["reward"]
        if r.get("profile") in ("state-potential-v3","state-potential-v4"):
            h=max(0.,s["altitude"])
            target=self.takeoff_altitude if self.phase=="takeoff" else 0.
            velocity=s["velocity"].copy()
            if self.phase=="takeoff":velocity[2]-=self.takeoff_velocity
            lateral_speed=r.get("potential_horizontal_speed",0.)*np.linalg.norm(velocity[:2])
            return -(r["potential_height"]*abs(target-h)+r["potential_speed"]*np.linalg.norm(velocity)+lateral_speed+r["potential_tilt"]*(1-np.cos(np.deg2rad(s["tilt"])))+r["potential_rate"]*np.linalg.norm(s["angular_velocity"])+r["potential_lateral"]*np.linalg.norm(s["position"][:2]-self._target()[:2]))
        return -np.linalg.norm(self._target()-s["position"])

    def step(self, action):
        old = self.last_state
        s = self.physics.step(action)
        m, r = self.cfg["mission"], self.cfg["reward"]
        speed = float(np.linalg.norm(s["velocity"]))
        distance = float(np.linalg.norm(s["position"][:2]-np.array(m["pad"][:2])))
        reason = None
        phase_changed = False
        if self.phase == "takeoff" and s["altitude"] >= self.takeoff_altitude:
            if abs(s["velocity"][2]-self.takeoff_velocity) > m["takeoff_velocity_tolerance"]:
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
        timeout=m["timeout"]*(.2+.8*self.episode_difficulty) if self.mission=="landing" else m["timeout"]
        if reason is None and s["t"] >= timeout:
            reason = "timeout"
        potential = self._potential(s)
        progress = 0. if phase_changed else potential-self.previous_potential
        vertical_error = s["velocity"][2]-self.takeoff_velocity if self.phase=="takeoff" else speed*max(0.1, 1-min(s["altitude"]/100, 1))
        dt = s["t"]-old["t"]
        reward = r["progress"]*progress - dt*(r["velocity"]*vertical_error**2 + r["tilt"]*np.deg2rad(s["tilt"])**2 + r["angular_velocity"]*np.linalg.norm(s["angular_velocity"])**2 + r["position"]*distance + r["alive"]) - r["fuel"]*(old["fuel_mass"]-s["fuel_mass"])
        if r.get("profile") in ("state-potential-v3","state-potential-v4"):
            # Difference of physical-state potentials, plus bounded running
            # costs. No PID action, optimal-control reference or expert data.
            reward=progress-dt*(r.get("time_cost",.3)+r["tilt"]*(1-np.cos(np.deg2rad(s["tilt"])))+r["angular_velocity"]*np.linalg.norm(s["angular_velocity"])**2+r["action_cost"]*float(np.dot(np.asarray(action)[1:],np.asarray(action)[1:]))) - r["fuel"]*(old["fuel_mass"]-s["fuel_mass"])
        if reason:
            reward += r["success"] if reason=="success" else r["failure"]
            terminal_speed=abs(s["velocity"][2]-self.takeoff_velocity) if self.phase=="takeoff" else speed
            reward-=r["terminal_speed"]*min(terminal_speed**2,400)+r["terminal_tilt"]*np.deg2rad(s["tilt"])**2+r["terminal_position"]*min(distance,100)
        self.total_reward += reward
        self.previous_potential, self.last_state = potential, s
        info = dict(outcome=reason, failure_reason=None if reason in (None,"success") else reason,
                    touchdown_speed=speed, tilt=s["tilt"], pad_distance=distance,
                    fuel_used=self.cfg["vehicle"]["fuel_mass"]*self.physics.mass_scale-s["fuel_mass"], phase=self.phase,
                    episode_difficulty=self.episode_difficulty)
        self.last_info = info
        return self._obs(s), float(reward), reason is not None and reason!="timeout", reason=="timeout", info

class LandingEnv(RocketEnv):
    def __init__(self, **kwargs): super().__init__("landing", **kwargs)

class TakeoffEnv(RocketEnv):
    def __init__(self, **kwargs): super().__init__("takeoff", **kwargs)
