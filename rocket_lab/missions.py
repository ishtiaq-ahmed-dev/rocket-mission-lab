"""Resolve user mission geometry without modifying the baseline configuration."""
import copy
from .schemas import FlightPlan


def configure_flight(config, flight_plan=None, mission='landing'):
    cfg=copy.deepcopy(config)
    m=cfg['mission']
    plan=FlightPlan.model_validate(flight_plan) if flight_plan is not None else FlightPlan(
        launch=m.get('launch',m['pad'][:2]), landing=m['pad'][:2], separation_altitude=m['takeoff_altitude'],profile=m.get('profile','research'))
    # Preserve baseline identities for archived, unmodified single-stage tasks.
    if flight_plan is not None:
        m.update(launch=list(plan.launch),pad=[*plan.landing,0.],takeoff_altitude=plan.separation_altitude,profile=plan.profile)
        m['timeout']=max(m['timeout'],240.,float(plan.separation_altitude)*0.25)
    if mission=='combined':
        cfg['vehicle']['upper_stage_mass']=2500. # generic unpowered payload; not an orbital stage model
    if plan.profile=='suborbital':
        # A separate generic vehicle sizing, never stretch the 16 t reserve
        # demonstration into a spaceflight by scaling its animation clock.
        # This generic vehicle has no specified pressure-dependent engine parameters.
        cfg['vehicle'].update(fuel_mass=140000.,max_thrust=3200000.,thrust_vacuum=3200000.,
                              nozzle_exit_area=0.,min_throttle=.06,isp=360.,isp_sea_level=360.,isp_vacuum=360.)
        cfg['world'].update(gravity_model='inverse_square',earth_radius=6371000.,atmosphere_model='layered')
        vehicle=cfg['vehicle']
        launch_mass=vehicle['dry_mass']+vehicle['fuel_mass']+vehicle.get('upper_stage_mass',0.)
        # Reserve acceleration margin for launch transients, drag and the randomized vehicle mass/thrust.
        ascent_acceleration=.8*(vehicle['max_thrust']/launch_mass-cfg['world']['gravity'])
        m.update(takeoff_velocity=min(1500.,(2*ascent_acceleration*plan.separation_altitude)**.5),takeoff_acceleration=18.,timeout=1200.,bounds=500000.,
                 high_altitude_recovery=True,launch=list(plan.launch),pad=[*plan.landing,0.],
                 takeoff_altitude=plan.separation_altitude)
        cfg['training'].update(observation_position_scale=[500.,500.,150000.],
                               observation_velocity_scale=[100.,100.,2000.])
    return cfg,plan
