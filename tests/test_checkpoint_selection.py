import copy
import pytest
from rocket_lab import storage


def test_selection_uses_largest_sample_and_excludes_changed_physics_and_future_regressions(tmp_path,monkeypatch):
    cfg={'vehicle':{'mass':10},'world':{'gravity':9.8},'mission':{'altitude':200}}
    monkeypatch.setattr(storage,'DATA',tmp_path)
    monkeypatch.setattr(storage,'load_config',lambda:cfg)
    monkeypatch.setattr(storage,'config_hash',lambda:'baseline')
    def checkpoint(identifier,steps,successes,config=None):
        return dict(id=identifier,job_id=identifier.split('__')[0],steps=steps,mission='landing',evaluation_episodes=20,successes=successes,config=config or copy.deepcopy(cfg),config_hash='variant',mean_reward=1e9)
    wrong=copy.deepcopy(cfg);wrong['vehicle']['mass']=1
    items=[checkpoint('a__early',100,3),checkpoint('a__best',200,5),checkpoint('a__later',300,1),
           checkpoint('b__best',150,6),checkpoint('wrong__best',1000,20,wrong)]
    monkeypatch.setattr(storage,'checkpoints',lambda mission=None:items)
    for identifier,k in [('a__best',80),('b__best',29)]:
        storage.atomic_json(tmp_path/'results'/f'{identifier}.json',dict(mission='landing',checkpoint_id=identifier,scenario='nominal',config_hash='baseline',episodes=256,successes=k,mean_touchdown_speed=2.,mean_tilt=4.,mean_pad_distance=5.))
    assert storage.select_checkpoint('landing',4)['id']=='a__best'
    assert storage.select_checkpoint('landing',3)['steps']<=200
    assert storage.select_checkpoint('landing',1)['id']=='a__early'
    # A large result from altered dynamics must not enter a nominal ranking.
    storage.atomic_json(tmp_path/'results'/'incompatible.json',dict(mission='landing',checkpoint_id='b__best',scenario='nominal',config_hash='different-physics',episodes=10000,successes=10000))
    assert storage.select_checkpoint('landing',4)['id']=='a__best'


def test_selection_prefers_the_hardest_envelope_a_checkpoint_still_flies(tmp_path,monkeypatch):
    cfg={'vehicle':{},'world':{},'mission':{}}
    monkeypatch.setattr(storage,'DATA',tmp_path);monkeypatch.setattr(storage,'load_config',lambda:cfg)
    monkeypatch.setattr(storage,'config_hash',lambda:'baseline')
    def stage(identifier,steps,difficulty,successes):
        return dict(id=identifier,job_id=identifier.split('__')[0],steps=steps,mission='landing',config=cfg,config_hash='baseline',
                    evaluation_episodes=12,successes=0,stage_difficulty=difficulty,stage_successes=successes,stage_evaluation_episodes=12)
    def full_mission(identifier,steps,successes):
        return dict(id=identifier,job_id=identifier.split('__')[0],steps=steps,mission='landing',config=cfg,config_hash='baseline',
                    evaluation_episodes=20,successes=successes)
    working=stage('a__working',100,.025,10);collapsed=stage('a__collapsed',500,.05,0);advanced=stage('a__advanced',700,.5,11)
    landed=full_mission('b__landed',900,20);crashed=full_mission('c__crashed',950,2)
    # Both policies were trained at a curriculum stage; the later one died after
    # the difficulty bump, so it must not outrank the stage that still flies.
    monkeypatch.setattr(storage,'checkpoints',lambda mission=None:[working,collapsed])
    assert storage.select_checkpoint('landing',4)['id']=='a__working'
    # The most advanced stage that still clears the bar wins.
    monkeypatch.setattr(storage,'checkpoints',lambda mission=None:[working,collapsed,advanced])
    assert storage.select_checkpoint('landing',4)['id']=='a__advanced'
    # A full-envelope landing outranks every curriculum-stage hop.
    monkeypatch.setattr(storage,'checkpoints',lambda mission=None:[working,collapsed,advanced,landed])
    assert storage.select_checkpoint('landing',4)['id']=='b__landed'
    # A full-mission policy that mostly crashes does not.
    monkeypatch.setattr(storage,'checkpoints',lambda mission=None:[working,crashed])
    assert storage.select_checkpoint('landing',4)['id']=='a__working'


def test_selection_does_not_treat_slow_failed_ascent_as_good_landing(tmp_path,monkeypatch):
    cfg={'vehicle':{},'world':{},'mission':{}}
    monkeypatch.setattr(storage,'DATA',tmp_path);monkeypatch.setattr(storage,'load_config',lambda:cfg)
    monkeypatch.setattr(storage,'config_hash',lambda:'baseline')
    items=[dict(id=f'ascent__{step}',job_id='ascent',steps=step,config=cfg,config_hash='baseline',evaluation_episodes=20,successes=10) for step in (100,200)]
    monkeypatch.setattr(storage,'checkpoints',lambda mission=None:items)
    for item,speed in zip(items,(0.,25.)):
        storage.atomic_json(tmp_path/'results'/f"{item['steps']}.json",dict(mission='takeoff',checkpoint_id=item['id'],scenario='nominal',config_hash='baseline',episodes=20,successes=10,mean_touchdown_speed=speed,mean_tilt=2.,mean_pad_distance=2.))
    assert storage.select_checkpoint('takeoff',4)['steps']==200
    monkeypatch.setattr(storage,'checkpoints',lambda mission=None:[])
    with pytest.raises(ValueError,match='No trained'):storage.select_checkpoint('takeoff',4)
