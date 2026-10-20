def test_ppo_resume_preserves_steps_and_normalization(monkeypatch,tmp_path):
    import rocket_lab.train as module
    import rocket_lab.storage as storage
    import rocket_lab.evaluate as evaluation
    import rocket_lab.simulation as simulation
    from rocket_lab.config import load_config
    cfg=load_config();cfg["training"]["n_envs"]=1
    monkeypatch.setattr(module,"DATA",tmp_path)
    monkeypatch.setattr(storage,"DATA",tmp_path)
    monkeypatch.setattr(evaluation,"DATA",tmp_path)
    monkeypatch.setattr(simulation,"DATA",tmp_path)
    monkeypatch.setattr(module,"load_config",lambda:cfg)
    # Exporting dashboard story runs is unrelated to the training-resume gate.
    monkeypatch.setattr(simulation,"simulate",lambda *a,**kw:None)
    module.train(steps=512,job_id="resume-parent",eval_episodes=1,device="cpu")
    checkpoints=storage.checkpoints("landing")
    parent=max(checkpoints,key=lambda c:c["steps"])
    module.train(steps=512,job_id="resume-child",eval_episodes=1,device="cpu",resume=parent["id"])
    child=storage.read_json(tmp_path/"jobs"/"resume-child"/"status.json")
    assert child["status"]=="completed"
    assert child["steps"]>=parent["steps"]+512
    saved=storage.read_json(tmp_path/"jobs"/"resume-child"/"resume.json")
    assert saved["parent_checkpoint"]==parent["id"]
    resumed=max([c for c in storage.checkpoints() if c["job_id"]=="resume-child"],key=lambda c:c["steps"])
    assert (storage.checkpoint_path(resumed["id"])/"normalize.pkl").exists()

def test_actor_warm_start_keeps_a_fresh_critic_and_rejects_physics_changes(monkeypatch,tmp_path):
    import copy
    import torch
    import pytest
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    import rocket_lab.train as module
    import rocket_lab.storage as storage
    from rocket_lab.config import load_config
    from rocket_lab.envs import RocketEnv
    monkeypatch.setattr(module,"DATA",tmp_path);monkeypatch.setattr(storage,"DATA",tmp_path)
    cfg=load_config();parent_env=DummyVecEnv([lambda:RocketEnv(config=cfg,difficulty=0)])
    parent=PPO('MlpPolicy',parent_env,n_steps=8,batch_size=8,n_epochs=1,seed=12,device='cpu',policy_kwargs=dict(net_arch=[128,128]))
    parent.learn(16)
    path=tmp_path/'checkpoints'/'actor-parent'/'step-000000016';path.mkdir(parents=True)
    parent.save(path/'model.zip')
    storage.atomic_json(path/'checkpoint.json',dict(job_id='actor-parent',mission='landing',algorithm='PPO',steps=16,difficulty=.4,config=cfg))
    updated=copy.deepcopy(cfg);updated['reward']['profile']='state-potential-v4';updated['reward']['potential_horizontal_speed']=12
    child_env=DummyVecEnv([lambda:RocketEnv(config=updated,difficulty=0)])
    child=PPO('MlpPolicy',child_env,n_steps=8,batch_size=8,n_epochs=1,seed=34,device='cpu',policy_kwargs=dict(net_arch=[128,128]))
    critic={key:value.clone() for key,value in child.policy.state_dict().items() if 'value_net' in key}
    meta=module.warm_start_actor(child,'actor-parent__step-000000016','landing',updated)
    assert meta['steps']==16 and meta['difficulty']==.4
    for key,value in child.policy.state_dict().items():
        if key.startswith(('mlp_extractor.policy_net.','action_net.')) or key=='log_std':assert torch.equal(value,parent.policy.state_dict()[key])
    for key,value in critic.items():assert torch.equal(child.policy.state_dict()[key],value)
    assert len(child.policy.optimizer.state)==0
    invalid=copy.deepcopy(updated);invalid['vehicle']['max_thrust']+=1
    with pytest.raises(ValueError,match='physics'):module.warm_start_actor(child,'actor-parent__step-000000016','landing',invalid)
    parent_env.close();child_env.close()

def test_mixed_full_start_outcomes_do_not_advance_the_practice_stage():
    import time
    from rocket_lab.train import TrainingCallback
    from rocket_lab.config import load_config
    cfg=load_config();cfg['training']['curriculum_window']=4
    callback=TrainingCallback('callback-mixture-test','landing','PPO',100,config=cfg,initial_difficulty=.4)
    callback.milestones=[];callback.last_write=time.time()
    for _ in range(8):
        callback.locals={'dones':[True],'infos':[{'outcome':'success','episode_difficulty':1.,'episode':{'r':1.,'l':2}}]}
        callback._on_step()
    assert callback.difficulty==.4 and len(callback.recent)==0
    assert len(callback.history)==8 and all(ep['difficulty']==1. for ep in callback.history)

def test_optimizer_adaptation_rejects_task_or_credit_changes():
    import copy
    import pytest
    from rocket_lab.config import load_config
    from rocket_lab.train import validate_optimizer_adaptation
    cfg=load_config();new=copy.deepcopy(cfg)
    new['training'].update(profile='precision-test',learning_rate=.00005,ppo_target_kl=.005)
    validate_optimizer_adaptation(cfg,new)
    new['reward']['success']+=1
    with pytest.raises(ValueError,match='unchanged'):validate_optimizer_adaptation(cfg,new)
    new=copy.deepcopy(cfg);new['training']['ppo_gamma']=.999
    with pytest.raises(ValueError,match='permits only'):validate_optimizer_adaptation(cfg,new)

def test_optimizer_adaptation_preserves_initial_weights_and_saves_final_update(monkeypatch,tmp_path):
    import copy
    import torch
    from stable_baselines3 import PPO
    import rocket_lab.train as module
    import rocket_lab.storage as storage
    import rocket_lab.evaluate as evaluation
    import rocket_lab.simulation as simulation
    from rocket_lab.config import load_config
    cfg=load_config();cfg['training']['n_envs']=1
    changed=copy.deepcopy(cfg);changed['training'].update(profile='precision-test',learning_rate=.00005,ppo_target_kl=.005)
    for target in (module,storage,evaluation,simulation):monkeypatch.setattr(target,'DATA',tmp_path)
    monkeypatch.setattr(module,'load_config',lambda path=None:changed if path else cfg)
    monkeypatch.setattr(simulation,'simulate',lambda *a,**kw:None)
    module.train(steps=512,job_id='adapt-parent',eval_episodes=1,device='cpu')
    parent=next(value for value in storage.checkpoints() if value.get('snapshot_phase')=='post-update final')
    assert parent['id'].endswith('-final')
    before=PPO.load(storage.checkpoint_path(parent['id'])/'model.zip',device='cpu')
    assert before.policy.optimizer.state # the final post-rollout update was saved
    module.train(steps=512,job_id='adapt-child',eval_episodes=1,device='cpu',config_path='test-variant',adapt_optimizer_from=parent['id'])
    initial=next(value for value in storage.checkpoints() if value['job_id']=='adapt-child' and value['steps']==512)
    restored=PPO.load(storage.checkpoint_path(initial['id'])/'model.zip',device='cpu')
    for key,value in before.policy.state_dict().items():assert torch.equal(value,restored.policy.state_dict()[key])
    assert restored.learning_rate==.00005 and restored.target_kl==.005
    assert len(before.policy.optimizer.state)==len(restored.policy.optimizer.state)
    for key,old in before.policy.optimizer.state_dict()['state'].items():
        new=restored.policy.optimizer.state_dict()['state'][key]
        for field in ('step','exp_avg','exp_avg_sq'):assert torch.equal(old[field],new[field])
    last=next(value for value in storage.checkpoints() if value['job_id']=='adapt-child' and value.get('snapshot_phase')=='post-update final')
    learned=PPO.load(storage.checkpoint_path(last['id'])/'model.zip',device='cpu')
    assert not torch.equal(learned.policy.action_net.weight,restored.policy.action_net.weight)
