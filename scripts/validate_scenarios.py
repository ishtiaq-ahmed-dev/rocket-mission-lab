"""Scenario sweep: every mission must stay valid at any allowed site and separation.

A flight plan is user data, so the vehicle, the limits derived from it and the
flight itself must survive the whole published envelope. This sweep flies a
matrix of landing sites and separation altitudes with the classical controller
-- deterministic and always available -- and checks the properties that must
hold no matter where the pads are: finite telemetry, a legal outcome, a run
that actually ends, reset states inside the corridor the limits describe, and
for the combined mission a real separation plus a completed descent.
"""
from pathlib import Path
import json
import sys
import time
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA, load_config
from rocket_lab.simulation import simulate
from rocket_lab.schemas import Outcome
from rocket_lab.missions import configure_flight
from rocket_lab.storage import config_hash, dynamics_hash

# Distances are measured launch -> landing and stay inside the published
# +/- 10000 m coordinate envelope. Research plans are gated below 1500 m by the
# schema; the suborbital profile covers the high end.
SITES = [("same-pad", [0., 0.], 0.),
         ("short-hop", [700., 700.], 0.),
         ("cross-field", [-1800., 2400.], 0.),
         ("far-site", [6000., -4500.], 0.),
         ("envelope-edge", [7000., 7000.], 0.)]
RESEARCH_ALTITUDES = [80., 400., 900., 1500.]
SUBORBITAL_ALTITUDES = [10000., 150000.]


def cases():
    """Every (name, plan, mission) combination this sweep must fly."""
    out = []
    for name, landing, _ in SITES:
        for altitude in RESEARCH_ALTITUDES:
            plan = dict(launch=[0., 0.], landing=list(landing), separation_altitude=altitude, profile="research")
            for mission in ("landing", "takeoff", "combined"):
                out.append((f"{name}/{altitude:.0f}m/{mission}", dict(plan), mission))
    for altitude in SUBORBITAL_ALTITUDES:
        plan = dict(launch=[0., 0.], landing=[6000., -4500.], separation_altitude=altitude, profile="suborbital")
        for mission in ("takeoff", "combined"):
            out.append((f"suborbital/{altitude:.0f}m/{mission}", dict(plan), mission))
    return out


def invariants(result, mission, plan):
    """Structural failures only -- how well the controller flew is reported separately."""
    problems = []
    frames = result.frames
    if len(frames) < 20:
        problems.append(f"only {len(frames)} frames")
    if not frames:
        return problems
    for index, frame in enumerate(frames):
        values = [*frame.position, *frame.velocity, *frame.quaternion, *frame.angular_velocity,
                  *frame.gimbal, *frame.wind, frame.throttle, frame.fuel_mass, frame.mass, frame.t]
        values += [value for value in (frame.clearance, frame.contact_speed, frame.reward, frame.release_time) if value is not None]
        if frame.upper_stage is not None:
            values += [*frame.upper_stage.position, *frame.upper_stage.velocity, *frame.upper_stage.quaternion]
        if index and frame.t <= frames[index - 1].t:
            problems.append(f"non-increasing time at frame {index}")
        values = np.array(values)
        if not np.isfinite(values).all():
            problems.append(f"non-finite telemetry at frame {index}")
        if not 0. <= frame.throttle <= 1.:
            problems.append(f"throttle {frame.throttle:.3f} outside [0,1] at frame {index}")
        if frame.fuel_mass < -1e-6:
            problems.append(f"negative fuel at frame {index}")
        if frame.clearance is not None and frame.clearance < -0.01:
            problems.append(f"clearance {frame.clearance:.3f} below the surface at frame {index}")
    if result.run.outcome not in Outcome.__args__:
        problems.append(f"unknown outcome {result.run.outcome!r}")
    cfg, _ = configure_flight(load_config(), plan, mission)
    timeout = cfg['mission']['timeout']
    if mission == 'combined':
        timeout = max(timeout, cfg['mission'].get('combined_timeout', 240.))
    control_dt = cfg['world']['timestep'] * cfg['world']['control_substeps']
    if result.run.duration > timeout + control_dt + 1e-8:
        problems.append(f"ran {result.run.duration:.1f} s past the timeout")
    # A plan whose limits are wrong fails on the first step, before flying.
    if frames[0].clearance is not None and frames[0].clearance < -0.01:
        problems.append(f"reset {frames[0].clearance:.2f} m below the pad")
    if result.run.outcome in ("out_of_bounds", "timeout") and result.run.duration < 2.:
        problems.append(f"immediate {result.run.outcome} at {result.run.duration:.2f} s: limits do not fit the plan")
    if mission == "combined":
        if result.run.separation is None:
            problems.append("combined flight never separated")
        phases = {frame.phase for frame in frames}
        if phases != {"takeoff", "landing"}:
            problems.append(f"combined phases {sorted(phases)}")
    return problems


def main():
    rows, failures = [], 0
    started = time.time()
    for name, plan, mission in cases():
        t0 = time.time()
        try:
            result = simulate(mission, method="classical", seed=7, save=False, flight_plan=plan)
        except Exception as error:  # a raised exception is exactly the failure being hunted
            failures += 1
            rows.append(dict(case=name, mission=mission, plan=plan, error=f"{type(error).__name__}: {error}"))
            print(f"FAIL {name}: {type(error).__name__}: {error}", flush=True)
            continue
        problems = invariants(result, mission, plan)
        run = result.run
        rows.append(dict(case=name, mission=mission, plan=plan, outcome=run.outcome,
                         duration=run.duration, touchdown_speed=run.touchdown_speed,
                         pad_distance=run.pad_distance, fuel_used=run.fuel_used,
                         frames=len(result.frames), problems=problems))
        status = "ok  " if not problems else "FAIL"
        if problems:
            failures += 1
        print(f"{status} {name:<34} {run.outcome:<14} t={run.duration:6.1f}s v={run.touchdown_speed:5.2f} "
              f"miss={run.pad_distance:7.2f}m fuel={run.fuel_used:8.0f}kg {'; '.join(problems)}", flush=True)
        rows[-1]["seconds"] = round(time.time() - t0, 2)
    report = dict(scope="classical controller sweep over the published flight-plan envelope",
                  config_hash=config_hash(), dynamics_hash=dynamics_hash(), seed=7,
                  elapsed_seconds=round(time.time() - started, 1), cases=len(rows), failures=failures, results=rows)
    (DATA / "scenario-validation.json").write_text(json.dumps(report, indent=1))
    print(f"\n{len(rows)} scenarios, {failures} structural failures, {report['elapsed_seconds']}s")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
