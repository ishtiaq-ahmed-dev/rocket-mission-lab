import gymnasium as gym
import copy
from gymnasium import spaces
import numpy as np
from scipy.spatial.transform import Rotation
from .physics import RocketPhysics
from .config import load_config

class RocketEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, mission="landing", config=None, difficulty=1.0, randomize=True, noise=True, training=False):
        super().__init__()
        self.cfg = copy.deepcopy(config or load_config())
        if mission=='combined':self.cfg['vehicle'].setdefault('upper_stage_mass',2500.)
        self.mission = mission
        self.difficulty = difficulty
        self.episode_difficulty = difficulty
        self.training = training
        self.takeoff_altitude=self.cfg["mission"]["takeoff_altitude"]
        self.takeoff_velocity=self.cfg["mission"]["takeoff_velocity"]
        probability=self.cfg["training"].get("full_start_probability",0.)
        if not 0<=probability<=1:raise ValueError("full_start_probability must be within [0,1]")
        self.randomize, self.noise = randomize, noise
        reward=self.cfg['reward']
        cost=reward.get('ground_speed_cost',0.)
        height=reward.get('ground_speed_height',50.)
        if not np.isfinite(cost) or cost<0 or (cost>0 and (not np.isfinite(height) or height<=0)):
            raise ValueError('Ground speed cost must be nonnegative and its height positive and finite')
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
        if self.training and self.mission in ('takeoff','combined') and settings.get("takeoff_goal_curriculum",False):
            start_height=settings["takeoff_curriculum_altitude"]
            start_velocity=settings["takeoff_curriculum_velocity"]
            if not 0<start_height<=m["takeoff_altitude"] or not 0<start_velocity<=m["takeoff_velocity"]:
                raise ValueError("Takeoff curriculum goals must be positive and within the full mission")
            self.takeoff_altitude=start_height+d*(m["takeoff_altitude"]-start_height)
            self.takeoff_velocity=start_velocity+d*(m["takeoff_velocity"]-start_velocity)
        self.phase = "takeoff" if self.mission in ("takeoff", "combined") else "landing"
        self.separated = False
        self.staging_pending = False
        self.separation = None
        self.launch=np.array(m.get('launch',m['pad'][:2]),dtype=float)
        self.landing=np.array(m['pad'][:2],dtype=float)
        if self.training and settings.get('target_curriculum',False):
            self.landing=self.launch+d*(self.landing-self.launch)
        self.retargets=[]
        self.auto_retarget=None
        self.retarget_applied=False
        self.landing_elapsed=0.0
        probability=float(settings.get('retarget_probability',0.) or 0.)
        if not 0<=probability<=1:raise ValueError('retarget_probability must be within [0,1]')
        # Mid-flight target changes are a training-only perturbation. A policy
        # that only ever sees the landing pad in its reset observation cannot
        # learn to divert, so this samples a new target once per landing.
        # Use a separate seeded stream: consuming the shared reset RNG here
        # would shift every later state/noise draw and break the guarantee
        # that training and evaluation share identical seeded episodes when
        # the perturbation is not triggered.
        if self.training and self.randomize and self.mission in ('landing','combined') and probability>0:
            retarget_rng=np.random.default_rng(seed) if seed is not None else self.np_random
            if retarget_rng.random()<probability:
                self.auto_retarget=dict(delay=float(retarget_rng.uniform(2.,6.)),offset=float(retarget_rng.uniform(15.,max(15.,settings.get('retarget_max_offset',60.)))*max(.35,d)),angle=float(retarget_rng.uniform(0.,2*np.pi)))
        if self.phase == "landing":
            # The first curriculum stage is genuinely easy: 3 m, -0.8 m/s,
            # centered and upright. d=1 preserves the complete mission ranges.
            h = 3. + d*(rng.uniform(*m["landing_altitude"])-3.)
            pos = [*(self.launch+rng.uniform(-m["horizontal_position"]*d, m["horizontal_position"]*d, 2)), h+self.physics.half]
            vel = [*rng.uniform(-m["horizontal_velocity"]*d, m["horizontal_velocity"]*d, 2), -.8+d*(rng.uniform(*m["landing_vertical_velocity"])+.8)]
        else:
            pos, vel = [*self.launch, self.physics.half], [0, 0, 0]
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
        xy=self.launch if self.phase=='takeoff' else self.landing
        return np.array([*xy, self.physics.half + (self.takeoff_altitude if self.phase == "takeoff" else 0.)])

    def command_landing(self, landing):
        """Move the landing target during a flight; keeps the physical state."""
        target=np.asarray(landing,dtype=float)
        if target.shape!=(2,) or not np.isfinite(target).all() or np.abs(target).max()>10000:
            raise ValueError('Landing target must be two finite local coordinates within +/- 10000 meters')
        previous=tuple(float(x) for x in self.landing)
        self.landing=target.copy()
        event=dict(t=float(self.physics.data.time),previous_landing=previous,landing=tuple(float(x) for x in target))
        self.retargets.append(event)
        # A target change is not progress and must not inject a potential spike
        # into the optimizer; the next difference is measured from the new goal.
        self.previous_potential=self._potential(self.last_state)
        return event

    def _obs(self, s):
        # Only physical state, clock and relative goal. No controller/expert action.
        train=self.cfg["training"]
        position_scale=np.asarray(train.get("observation_position_scale",[400,400,400]))
        velocity_scale=np.asarray(train.get("observation_velocity_scale",[50,50,50]))
        origin=np.array([*self.launch,0.])
        obs = np.concatenate([(np.asarray(s["position"])-origin)/position_scale, np.asarray(s["velocity"])/velocity_scale,
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
            world=self.cfg['world']
            if 'position_noise_m' in world:
                obs[:3]-=noise[:3]*400/position_scale
                obs[:3]+=noise[:3]*world['position_noise_m']/max(world['sensor_noise'],1e-12)/position_scale
                # The commanded site is known; relative position shares the
                # navigation error rather than inventing an independent GPS.
                obs[15:18]=(self._target()-origin)/position_scale-obs[:3]
            if 'velocity_noise_m_s' in world:
                obs[3:6]-=noise[3:6]*50/velocity_scale
                obs[3:6]+=noise[3:6]*world['velocity_noise_m_s']/max(world['sensor_noise'],1e-12)/velocity_scale
        self.sensed_state={**s,"position":obs[:3]*position_scale+origin,"velocity":obs[3:6]*velocity_scale,"angular_velocity":obs[10:13]*2}
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
        if self.staging_pending:
            action = np.asarray(action, dtype=float).copy()
            action[0] = -1. # interstage cannot release with the main engine firing
        s = self.physics.step(action)
        if self.phase=='landing':
            self.landing_elapsed+=max(0.,s['t']-old['t'])
        if self.auto_retarget is not None and not self.retarget_applied and self.phase=='landing':
            minimum=float(self.cfg['training'].get('retarget_min_altitude',45.))
            if self.landing_elapsed>=self.auto_retarget['delay'] and s['altitude']>minimum:
                self.retarget_applied=True
                angle,radius=self.auto_retarget['angle'],self.auto_retarget['offset']
                landing=self.landing+np.array([np.cos(angle),np.sin(angle)])*radius
                self.command_landing(np.clip(landing,-9999.,9999.))
        m, r = self.cfg["mission"], self.cfg["reward"]
        speed = float(np.linalg.norm(s["velocity"]))
        distance = float(np.linalg.norm(s["position"][:2]-self._target()[:2]))
        reason = None
        phase_changed = False
        if self.phase == "takeoff" and s["altitude"] >= self.takeoff_altitude and not self.staging_pending:
            if abs(s["velocity"][2]-self.takeoff_velocity) > m["takeoff_velocity_tolerance"]:
                reason = "crash_speed"
            elif s["tilt"] >= m["touchdown_tilt_deg"]:
                reason = "crash_tilt"
            elif distance > m["pad_radius"]:
                reason = "missed_pad"
            elif self.mission == "combined":
                self.staging_pending = True
            else:
                reason = "success"
        if self.staging_pending and (s['throttle'] <= 1e-8 or not m.get('separation_shutdown', False)):
            self.separation=self.physics.separate()
            self.phase, self.separated, phase_changed = "landing", True, True
            self.staging_pending=False
            self.landing_elapsed=0.
            s=self.physics.state()
            distance=float(np.linalg.norm(s['position'][:2]-self._target()[:2]))
        if s["clearance"] <= 1e-7 and reason is None and not self.physics.on_pad:
            if self.phase == "takeoff":
                reason = "crash_speed"
            elif max(speed, s['contact_speed']) >= m["touchdown_speed"]:
                reason = "crash_speed"
            elif s["tilt"] >= m["touchdown_tilt_deg"]:
                reason = "crash_tilt"
            elif distance > m.get('landing_tolerance',m["pad_radius"]):
                reason = "missed_pad"
            else:
                reason = "success"
        if reason is None and s["fuel_mass"] <= 0:
            reason = "out_of_fuel"
        corridor=max(np.linalg.norm(s['position'][:2]-self.launch),np.linalg.norm(s['position'][:2]-self.landing))
        allowed=m['bounds']+np.linalg.norm(self.launch-self.landing)
        if reason is None and (corridor > allowed or s["altitude"] > m["bounds"]):
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
        if self.phase=='landing' and r.get('ground_speed_cost',0)>0:
            # Dense physical speed cost close to the surface; no reference
            # velocity, controller action or expert trajectory is provided.
            proximity=max(0.,1-max(0.,s['altitude'])/r.get('ground_speed_height',50.))
            reward-=dt*r['ground_speed_cost']*proximity**2*speed**2
        self.total_reward += reward
        self.previous_potential, self.last_state = potential, s
        info = dict(outcome=reason, failure_reason=None if reason in (None,"success") else reason,
                    touchdown_speed=speed, tilt=s["tilt"], pad_distance=distance,
                    fuel_used=self.cfg["vehicle"]["fuel_mass"]*self.physics.mass_scale-s["fuel_mass"], phase=self.phase,
                    episode_difficulty=self.episode_difficulty,retargets=list(self.retargets))
        self.last_info = info
        return self._obs(s), float(reward), reason is not None and reason!="timeout", reason=="timeout", info

class LandingEnv(RocketEnv):
    def __init__(self, **kwargs): super().__init__("landing", **kwargs)

class TakeoffEnv(RocketEnv):
    def __init__(self, **kwargs): super().__init__("takeoff", **kwargs)
