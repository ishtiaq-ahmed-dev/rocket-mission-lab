from rocket_lab.storage import atomic_json,read_json
from rocket_lab.schemas import FlightPlan


def test_worker_claims_api_dispatch_without_mistaking_it_for_a_resumed_campaign(monkeypatch,tmp_path):
    import rocket_lab.campaign as campaign
    monkeypatch.setattr(campaign,'DATA',tmp_path)
    plan=FlightPlan().model_dump(mode='json')
    folder=tmp_path/'campaigns'/'dispatch-test'
    atomic_json(folder/'plan.json',plan)
    atomic_json(folder/'status.json',dict(status='starting',budget=4096,steps=0,missions={}))
    (folder/'stop').touch()
    campaign.run_campaign('dispatch-test',4096,4096,plan)
    status=read_json(folder/'status.json')
    assert status['status']=='stopped' and set(status['missions'])=={'landing','takeoff','combined'}
    assert status['dynamics_hash'] and status['steps']==0


def test_failed_campaign_recovers_only_compatible_saved_steps(monkeypatch,tmp_path):
    import rocket_lab.campaign as campaign
    monkeypatch.setattr(campaign,'DATA',tmp_path)
    identity=campaign.dynamics_hash()
    checkpoint=dict(job_id='failed-landing-r0',mission='landing',steps=4096,
                    dynamics_hash=identity,id='failed-landing-r0__step-000004096')
    monkeypatch.setattr(campaign,'checkpoints',lambda:[checkpoint])
    tasks={mission:dict(steps=0,best_successes=-1,plateau=0,qualified=False,checkpoint_id=None)
           for mission in ('landing','takeoff','combined')}
    folder=tmp_path/'campaigns'/'recover-test'
    atomic_json(folder/'status.json',dict(id='recover-test',status='failed',budget=4096,steps=0,
        missions=tasks,active_job='failed-landing-r0',dynamics_hash=identity,
        flight_plan=FlightPlan().model_dump(mode='json')))
    campaign.run_campaign('recover-test',4096,4096,resume=True)
    status=read_json(folder/'status.json')
    assert status['steps']==4096 and status['status']=='budget_exhausted'
    assert status['missions']['landing']['latest_checkpoint_id']==checkpoint['id']
    assert status['recovery']['restored_steps']==4096


def test_failed_campaign_rejects_changed_dynamics(monkeypatch,tmp_path):
    import pytest
    import rocket_lab.campaign as campaign
    monkeypatch.setattr(campaign,'DATA',tmp_path)
    atomic_json(tmp_path/'campaigns'/'obsolete'/'status.json',dict(status='failed',dynamics_hash='obsolete'))
    with pytest.raises(ValueError,match='Dynamics changed'):
        campaign.run_campaign('obsolete',4096,4096,resume=True)
