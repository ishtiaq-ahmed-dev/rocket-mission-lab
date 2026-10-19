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
