from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
import math


def validate_site_separation(launch,landing):
    """New operational plans require distinct pads; archived plans remain readable."""
    if math.dist(launch,landing)<=1000.:
        raise ValueError('Takeoff and landing pads must be more than 1000 meters apart')

class FlightPlan(BaseModel):
    """Local meters on the flat z=0 surface, x east and y north."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    launch: tuple[float, float] = (0., 0.)
    landing: tuple[float, float] = (0., 0.)
    separation_altitude: float = Field(default=400., ge=80, le=150000)
    profile: Literal['research','suborbital'] = 'research'

    @model_validator(mode='after')
    def profile_envelope(self):
        if self.profile=='research' and self.separation_altitude>1500:
            raise ValueError('Low-altitude research separation must be within 80 to 1500 meters')
        if self.profile=='suborbital' and self.separation_altitude<10000:
            raise ValueError('Suborbital research separation must be within 10000 to 150000 meters')
        return self

    @field_validator('launch', 'landing')
    @classmethod
    def bounded_coordinates(cls, value):
        if any(abs(x)>10000 for x in value):
            raise ValueError('Coordinates must be within +/- 10000 meters')
        return value

class TargetUpdate(BaseModel):
    """A landing target issued during flight, in local surface meters."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    time: float = Field(ge=0)
    landing: tuple[float, float]

    @field_validator('landing')
    @classmethod
    def bounded_target(cls, value):
        if any(abs(x)>10000 for x in value):
            raise ValueError('Coordinates must be within +/- 10000 meters')
        return value

class RetargetEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    t: float
    previous_landing: tuple[float, float]
    landing: tuple[float, float]

class Separation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    t: float
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]
    mass: float

Mission = Literal["landing", "takeoff", "combined"]
Outcome = Literal["success", "crash_speed", "crash_tilt", "missed_pad", "out_of_fuel", "timeout", "out_of_bounds"]

class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    t: float
    position: tuple[float,float,float]
    quaternion: tuple[float,float,float,float]
    velocity: tuple[float,float,float]
    angular_velocity: tuple[float,float,float]
    throttle: float = Field(ge=0,le=1)
    gimbal: tuple[float,float]
    fuel_mass: float = Field(ge=0)
    mass: float = Field(gt=0)
    wind: tuple[float,float,float]
    phase: Literal["landing","takeoff"]
    reward: float | None = None
    clearance: float | None = None
    contact_speed: float | None = None
    hold_down: bool | None = None
    release_time: float | None = None
    upper_stage: 'StageState | None' = None

class StageState(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    position: tuple[float,float,float]
    velocity: tuple[float,float,float]
    quaternion: tuple[float,float,float,float]
    impacted: bool = False

class RunMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    mission: Mission
    method: Literal["classical","rl"]
    level: int = Field(ge=1,le=4)
    checkpoint_steps: int | None = None
    checkpoint_id: str | None = None
    difficulty: float = Field(default=1.0,ge=0,le=1)
    training_mode: bool = False
    target_altitude: float | None = None
    target_velocity: float | None = None
    algorithm: str | None = None
    seed: int
    outcome: Outcome
    failure_reason: Outcome | None
    touchdown_speed: float
    tilt: float
    pad_distance: float
    fuel_used: float
    duration: float
    total_reward: float
    source: str = "MuJoCo simulation"
    controller_status: str | None = None
    flight_plan: FlightPlan | None = None
    initial_flight_plan: FlightPlan | None = None
    landing_tolerance: float | None = None
    launch_release_time: float | None = None
    separation: Separation | None = None
    retargets: list[RetargetEvent] = Field(default_factory=list)
    dynamics_hash: str | None = None

class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Accept archived 1.0 flights; new producers identify goal/provenance fields.
    schema_version: Literal["1.0","1.1"] = "1.1"
    config_hash: str
    rocket_length: float
    launch_stand_height: float = 0.0
    initial_fuel: float
    min_throttle: float | None = None
    max_thrust: float | None = None
    gravity_model: str | None = None
    run: RunMeta
    frames: list[Frame]

class SimRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    mission: Mission = "landing"
    method: Literal["classical","rl"] = "classical"
    level: int = Field(default=4,ge=1,le=4)
    seed: int = Field(default=42,ge=0,le=2147483647)
    checkpoint_id: str | None = None
    flight_plan: FlightPlan | None = None
    retarget: TargetUpdate | None = None
    retargets: list[TargetUpdate] = Field(default_factory=list,max_length=32)

    @model_validator(mode='after')
    def operational_sites(self):
        plan=self.flight_plan or FlightPlan(landing=(1200.,400.),separation_altitude=600.)
        validate_site_separation(plan.launch,plan.landing)
        for command in [*self.retargets,*([self.retarget] if self.retarget else [])]:
            validate_site_separation(plan.launch,command.landing)
        self.flight_plan=plan
        return self

class TrainRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    mission: Mission = "landing"
    algorithm: Literal["PPO","SAC"] = "PPO"
    steps: int = Field(default=100000,ge=1000,le=100000000)
    seed: int = Field(default=42,ge=0,le=2147483647)
    device: Literal["cpu","cuda","auto"] = "auto"
    flight_plan: FlightPlan | None = None

    @model_validator(mode='after')
    def operational_sites(self):
        if self.flight_plan:validate_site_separation(self.flight_plan.launch,self.flight_plan.landing)
        return self
