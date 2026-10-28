import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from rocket_lab.schemas import SimRequest,TrainRequest,FlightPlan
from rocket_lab.isaac.launcher import NativeStart
from rocket_lab.isaac.stream import TelemetryServer,exchange


@pytest.mark.parametrize('model',[SimRequest,TrainRequest,NativeStart])
@pytest.mark.parametrize('distance',[0.,999.99,1000.])
def test_new_operational_requests_reject_touching_one_km_boundary(model,distance):
    plan=dict(launch=[500.,-300.],landing=[500.+distance,-300.])
    with pytest.raises(ValidationError,match='more than 1000'):
        model(**(plan if model is NativeStart else dict(flight_plan=plan)))


def test_default_and_translated_valid_plan_preserve_archived_small_site_geometry():
    for settings in (SimRequest().flight_plan,NativeStart()):
        assert settings.landing==(1200.,400.) and settings.separation_altitude==600.
    assert SimRequest(flight_plan=dict(launch=[500,-300],landing=[1500.01,-300])).flight_plan.landing==(1500.01,-300.)
    assert FlightPlan(launch=[0,0],landing=[80,40]).landing==(80.,40.)


def test_http_and_live_retarget_cannot_bypass_pad_spacing():
    from rocket_lab.api import app
    client=TestClient(app)
    plan=dict(launch=[500,-300],landing=[1500,-300])
    for path in ('/simulate','/training','/campaigns'):
        assert client.post(path,json=dict(flight_plan=plan)).status_code==422
    assert client.post('/native/start',json=plan).status_code==422
    with pytest.raises(ValidationError,match='more than 1000'):
        SimRequest(retarget=dict(time=30,landing=[1000,0]))
    server=TelemetryServer(port=0).start()
    try:
        server.publish(dict(launch=[500,-300],landing=[1700,100],control_mode='guidance'))
        denied=exchange(dict(op='command',command=dict(type='retarget',landing=[1500,-300])),port=server.port)
        assert not denied['ok'] and list(server.drain())==[]
        accepted=exchange(dict(op='command',command=dict(type='retarget',landing=[1700,100])),port=server.port)
        assert accepted['ok'] and next(server.drain())['landing']==[1700,100]
    finally:server.close()
