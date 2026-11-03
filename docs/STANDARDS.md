# International-standard reference profile

Reviewed 2 November 2026. This profile defines what the browser replay and the
Python workbench can and cannot claim. It is a public-data reference, not a
flight-certification record.

## Scope

- **Browser replay** (`frontend/index.html`): a Falcon 9 Block 5-class RTLS
  mission from SLC-40 to LZ-1 with ascent, MECO, separation, second-stage
  insertion, boostback, entry burn, aerodynamic descent and landing.
- **Python workbench** (`rocket_lab/`, `config.yaml`): a separate 400 m
  subscale landing/takeoff/combined laboratory. Its vehicle is intentionally
  smaller and is not a Falcon 9 model.
- **Public data only.** No SpaceX proprietary telemetry, flight software,
  structural data or certification data is used.

## Standards applied

| Area | Reference | Applied in the replay |
| --- | --- | --- |
| Units and quantities | SI / ISO 80000 conventions | metres, kilograms, seconds, newtons, kelvin, radians; mission time is T+ seconds |
| Geodesy and gravity | WGS 84 defining constants | GM `3.986004418e14 m3/s2`, rotation `7.292115e-5 rad/s`, mean radius `6,371,008.8 m`; SLC-40 and LZ-1 coordinates are WGS-84 |
| Atmosphere | ISO 2533:1975 and U.S. Standard Atmosphere 1976 | layered geopotential model to 84.852 km; temperature, pressure, density and speed of sound; tabulated density extension above it |
| Propulsion | NASA specific-impulse relation | `mdot = T / (Isp * g0)`; pressure-dependent Merlin sea-level thrust through nozzle exit area |
| Vehicle anchors | Public SpaceX Falcon 9 figures | height, diameter, liftoff mass, payload class, nine Merlin 1D engines and one MVac |
| Mission geometry | Public launch/landing site coordinates | SLC-40 at 28.5619 N, 80.5773 W; LZ-1 at 28.48583 N, 80.54444 W |

The replay uses a **spherical mean-radius Earth** with WGS-84 GM and rotation.
It does not integrate the WGS-84 ellipsoid, geoid undulations, tides or
atmospheric refraction. Geographic coordinates use WGS-84, but ellipsoid
height is replaced by mean-sphere altitude.

ISO 2533:1975 defines the lower standard atmosphere; the 84.852 km layer top and
the upper density table follow the U.S. Standard Atmosphere 1976. The engine
pressure model is zero above the layered atmosphere.

## Public Falcon 9 Block 5 anchors

| Item | Public anchor | Replay value / result |
| --- | --- | --- |
| Height | 70.0 m | modeled geometry |
| Diameter | 3.7 m | 3.66 m reference diameter; area 10.52 m2 |
| Liftoff mass | 549,054 kg | 546,600 kg no-payload closure, 0.45% below |
| Payload to LEO | 22,800 kg | not used as the default mission payload |
| Payload to GTO | 8,300 kg | not used |
| First stage | 9 Merlin 1D | 9 engines; 411,000 kg propellant |
| Merlin 1D thrust | 845 kN sea level / 914 kN vacuum | sea-level 7.606 MN and vacuum 8.226 MN for nine engines |
| Merlin 1D Isp | 282 s sea level / 311 s vacuum | 311 s from `914 kN / (299.7 kg/s * g0)` |
| Second stage | 1 MVac, 107,500 kg propellant | 981 kN vacuum, 287.5 kg/s, 348 s |
| Fairing | 5.2 m diameter, 13.1 m length | 1,900 kg modeled mass |
| Default mission | 300 km-class insertion, 7,000 kg payload | 270 x 341 km at 39.5 deg, mean altitude about 305 km |

The model's no-payload mass is
`22,200 + 411,000 + 4,000 + 107,500 + 1,900 = 546,600 kg`. The default
mission adds a 7,000 kg payload. The 2,454 kg difference from the published
liftoff mass is 0.45%; stage dry mass is not published at the same level as the
top-level figures and remains a modeled input. The check therefore verifies
mass closure, not an exact stage-by-stage breakdown.

## Default-flight regression

These are simulated outputs, not measured SpaceX data:

| Quantity | Result |
| --- | --- |
| MECO | 71.9 km at 1.781 km/s |
| Booster apogee | 183.9 km |
| Second-stage insertion | 269.9 x 340.9 km at 39.54 deg |
| Touchdown | 1.82 m/s vertical, 0.03 m/s horizontal, 0.11 deg tilt |
| Pad offset | 0.2 m from LZ-1 centre on an 86 m pad |

The flight is flown by the neural policy ([FLIGHT-POLICY.md](FLIGHT-POLICY.md)).
The booster apogee is higher than in the earlier scripted replay (138.6 km)
because the boostback no longer thrusts 14 deg below the horizon; the extra
descent energy is removed by a stronger entry burn, as on Falcon 9.

Second-stage insertion is closed-loop: the network learned a teacher that drives
altitude toward 270 km with zero climb rate as horizontal speed approaches
circular, and cuts off at a 300 km semi-major axis. This is a modeled guidance
law, not an optimized or flight-certified trajectory.

## Executable checks

```powershell
node scripts/check_standards.js
node scripts/check_flight.js
.venv\Scripts\python.exe -m pytest tests -q
```

`check_standards.js` verifies 57 anchors: WGS-84 constants, ISO 2533/1976
temperature/pressure/density/sound-speed points, public Merlin and MVac thrust
and Isp, propellant masses, mass closure, site coordinates, and the default
orbit/landing regression. It writes `data/standards-validation.json`.

`check_flight.js` independently checks event ordering, propellant monotonicity,
throttle bounds, vis-viva consistency, insertion elements, touchdown limits,
that booster thrust never points toward the ground after separation, and that
the page contains no scripted guidance.

Passing these checks means the public anchors and internal invariants are
consistent. It does **not** mean the model can certify a launch, predict a real
flight, or establish landing reliability.

## What is not modeled or certified

- Rigid-body 6-DOF dynamics (attitude is a rate-limited first-order response),
  slosh, aeroelasticity, sensor noise, abort modes and weather.
- Structural loads, thermal protection, fatigue, engine transients, propellant
  conditioning and reusability inspection.
- FAA/range-safety analysis, airspace coordination, flight-termination systems
  and operational launch constraints.
- SpaceX guidance, navigation and control. The neural policy imitates an
  educational teacher; its 298/300 held-out rate is a simulation result.
- The Python laboratory's subscale RL policies, which did not qualify and are
  not the browser Falcon 9 mission.

## Sources

- [SpaceX Falcon 9](https://www.spacex.com/vehicles/falcon-9)
- [SpaceX Falcon User's Guide](https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf)
- [NGA WGS 84](https://earth-info.nga.mil/GandG/wgs84/index.html)
- [ISO 2533:1975](https://www.iso.org/standard/7472.html)
- [U.S. Standard Atmosphere 1976](https://www.ngdc.noaa.gov/stp/space-weather/online-publications/miscellaneous/us-standard-atmosphere-1976/us-standard-atmosphere_st76-1562_noaa.pdf)
- [NASA specific impulse](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/)
