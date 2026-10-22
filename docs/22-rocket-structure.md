# Rocket appearance restoration and structure review

Reviewed 21 October 2026. The user requested the original UI, rocket finish and coastal world, retained mission features, removal of four upper protrusions, and better lower supports.

## Primary sources examined

- [SpaceX Falcon Payload User's Guide, May 2025](https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf), sections 2.3–2.5 and the vehicle overview: tank construction, propulsion, stage interfaces and recovery hardware.
- [NASA Commercial Crew press kit](https://www.nasa.gov/commercial-crew-program-press-kit/), Falcon 9 section: recovery hardware stowage, first-stage propulsion and interstage function.
- [NASA launch and landing sequence](https://www.nasa.gov/wp-content/uploads/2020/08/falcon9_launch_and_landing.pdf): ascent, separation, attitude reversal, boostback, entry, aerodynamic guidance and final landing burn.

SpaceX describes separate fuel/oxidizer volumes in an aluminum-lithium tank structure, a composite interstage, nine first-stage engines arranged around a central engine, and a single vacuum engine on the second stage. It identifies four upper grid fins and four lower deployable legs. NASA also describes legs and fins stowed during ascent. These upper protrusions are recovery steering surfaces; removing them here follows the user's appearance preference.

This project's existing vehicle is a generic 40 m, single-thrust simulation. Its restored rounded cap, proportions and engine count are retained. It is not an exact Falcon 9 replica. Public overviews do not supply manufacturing dimensions for every bracket, joint, seal or internal mechanism. No private CAD, structural certification or exact proprietary landing-leg actuation is claimed.

## Component-by-component implementation

| Component | Current drawing and behavior | Model boundary |
| --- | --- | --- |
| Tank barrel / outer shell | Original white finish, seeded grain, lower soot, seams, rivet marks and branding | Finish marks are illustrative; internal LOX/RP-1 domes, plumbing and weld loads are not integrated |
| Circumferential joints | Original narrow metallic bands and service-line details | Visual joints rather than independent flexible sections |
| Upper end | Original rounded research-vehicle cap on standalone flights | Not a satellite fairing or Dragon spacecraft |
| Combined-flight interface | Dark interstage, attached upper-stage preview and recorded separation | Existing mass-release event remains; no ejection impulse or powered second-stage dynamics |
| Upper fins | Removed entirely from vehicle geometry | The simulator already lacks explicit grid-fin lift and actuators |
| Lower engine section | Original tapered dark skirt; central gimballed bell and cooling-ring details | One aggregate thrust axis, not nine separately modeled Merlin engines |
| Nozzle and exhaust | Bell, flame and smoke share the commanded gimbal direction; smoke begins at the bell exit | No turbopump, injector, combustion chemistry or CFD solver |
| Four leg roots | Radial lower hinges, pins and body hardpoints | Approximate geometry chosen to fit this vehicle |
| Leg shells | Fixed-length tapered shells rotate upward to stow and outward/downward to deploy | Their length never scales toward zero |
| Braces | Overlapping outer tube and inner rod extend between upper body mounts and foot hardpoints | Telescopic visual construction, not a claim about exact Falcon hardware |
| Feet | Broad dark soles with joint housings; rotate alongside the body during stowage | No separately integrated foot friction, compliance or crush core |
| Ground interface | Deployed foot centers at radial 6.2 m; soles at local Y = -20 m; nozzle exit at -19.4 m | 0.6 m nominal upright clearance; rigid-body contact and existing touchdown criteria remain authoritative |

## Deployment and support

The drawing derives deployment from recorded phase and ground clearance, so scrubbing, pausing and replaying yield the same pose. At rest the legs are fully deployed. During takeoff they fold between 1 and 18 m clearance. During descent they unfold between 100 and 35 m clearance and stay out through touchdown. These thresholds are simulator presentation choices, not a reproduction of flight-qualified SpaceX sequencing.

Each arm rotates about a fixed hinge. The foot follows that arm's circular path while its sole turns toward the ground. Two overlapping brace members bridge the body mount and moving foot. The deployed feet align with the existing contact-height convention; the nozzle is higher than the soles. A visual support assembly does not correct excessive touchdown speed or guarantee against toppling. A compliant four-contact landing dynamics model would require a separate physics change and new qualification.

## Restored world with movable sites

The original terrain, shoreline, grass, rocks, facilities, roads, ocean, HDR reflections and shadow lighting are active. Both pads follow the **applied** flight plan, not unsaved editor values. Prepared ground blends into the surrounding terrain, with a larger prepared radius in coarse distant mesh regions. Vegetation avoids the pad footprints. The offshore deck is kept separate from terrain earthworks. Camera ground clearance and smoke use the same scenery offset and surface convention. Physics still uses a flat ground contact plane, so surrounding visual hills are not collision terrain.

The original dashboard colors, typography, sidebar, panels and chart palette are restored. Coordinate editing, separation altitude, training campaigns, event jumps, keyboard movement, long-distance zoom and follow framing remain. Touchdown status sits below the viewport so it cannot cover the landing supports.

## Revision checks

Automated checks and browser observations are recorded below after verification. Historical flight evaluations remain attached to their original source/configuration identities. No physics/controller/training module was modified for this appearance revision.
