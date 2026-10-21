from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

class FlightPlan(BaseModel):
    """Local meters on the flat z=0 surface, x east and y north."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    launch: tuple[float, float] = (0., 0.)
    landing: tuple[float, float] = (0., 0.)
    separation_altitude: float = Field(default=400., ge=80, le=1500)

    @field_validator('launch', 'landing')
    @classmethod
    def bounded_coordinates(cls, value):
        if any(abs(x)>10000 for x in value):
            raise ValueError('Coordinates must be within +/- 10000 meters')
        return value

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
    separation: Separation | None = None
    dynamics_hash: str | None = None

class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Accept archived 1.0 flights; new producers identify goal/provenance fields.
    schema_version: Literal["1.0","1.1"] = "1.1"
    config_hash: str
    rocket_length: float
    initial_fuel: float
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

class TrainRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    mission: Mission = "landing"
    algorithm: Literal["PPO","SAC"] = "PPO"
    steps: int = Field(default=100000,ge=1000,le=100000000)
    seed: int = Field(default=42,ge=0,le=2147483647)
    device: Literal["cpu","cuda","auto"] = "auto"
    flight_plan: FlightPlan | None = None
