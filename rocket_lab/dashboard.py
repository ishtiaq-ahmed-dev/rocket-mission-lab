"""Small, page-specific dashboard payloads; detailed artifacts stay available."""
from .config import DATA
from .index_cache import cached_record
from .storage import checkpoints,training_jobs,runs

CHECKPOINT_FIELDS=('created_at','id','job_id','mission','algorithm','steps','success_rate',
    'mean_reward','evaluation_episodes','successes','qualification','dynamics_hash')


def compact_checkpoints():
    return [{key:value[key] for key in CHECKPOINT_FIELDS if key in value} for value in checkpoints()]


def dashboard(view='flight'):
    if view=='flight':return dict(checkpoints=compact_checkpoints())
    if view=='training':
        jobs=training_jobs()
        # Historical curves/episodes are fetched only when selected.
        return dict(checkpoints=compact_checkpoints(),jobs=[{**value,'curve':[],'episodes':[]} for value in jobs])
    return dict(runs=runs(),results=[value for path in (DATA/'results').glob('*.json') if (value:=cached_record(path))])
