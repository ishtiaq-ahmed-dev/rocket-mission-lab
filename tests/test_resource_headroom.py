from rocket_lab.resources import memory_headroom,memory_is_low

def test_memory_gate_uses_both_physical_and_commit_headroom():
    gib=1024**3
    assert memory_is_low(dict(physical_available=8*gib,commit_available=3*gib))
    assert memory_is_low(dict(physical_available=gib,commit_available=10*gib))
    assert not memory_is_low(dict(physical_available=8*gib,commit_available=10*gib))
    assert not memory_is_low(None)

def test_memory_probe_is_read_only_and_finite_when_available():
    value=memory_headroom()
    assert value is None or all(isinstance(item,int) and item>=0 for item in value.values())
