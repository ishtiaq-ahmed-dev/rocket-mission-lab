"""Resolve user mission geometry without modifying the baseline configuration."""
import copy
from .schemas import FlightPlan


def configure_flight(config, flight_plan=None, mission='landing'):
    cfg=copy.deepcopy(config)
    m=cfg['mission']
    plan=FlightPlan.model_validate(flight_plan) if flight_plan is not None else FlightPlan(
        launch=m.get('launch',m['pad'][:2]), landing=m['pad'][:2], separation_altitude=m['takeoff_altitude'])
    # Preserve baseline identities for archived, unmodified single-stage tasks.
    if flight_plan is not None:
        m.update(launch=list(plan.launch),pad=[*plan.landing,0.],takeoff_altitude=plan.separation_altitude)
        m['timeout']=max(m['timeout'],240.)
    if mission=='combined':
        cfg['vehicle']['upper_stage_mass']=2500. # generic unpowered payload; not an orbital stage model
    return cfg,plan
