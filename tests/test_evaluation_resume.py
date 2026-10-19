import pytest
from rocket_lab.evaluate import evaluate

def test_resumable_fixed_seed_evaluation(monkeypatch,tmp_path):
    import rocket_lab.evaluate as module
    monkeypatch.setattr(module,"DATA",tmp_path)
    first,rows=evaluate("landing",1,episodes=3,start_seed=10000,progress_id="resume-test")
    second,resumed=evaluate("landing",1,episodes=3,start_seed=10000,progress_id="resume-test")
    assert rows==resumed
    assert first["successes"]==second["successes"]
    assert len((tmp_path/"evaluations"/"resume-test"/"episodes.jsonl").read_text().splitlines())==3
    with pytest.raises(ValueError,match="source/config changed"):
        evaluate("landing",2,episodes=3,start_seed=10000,progress_id="resume-test")
