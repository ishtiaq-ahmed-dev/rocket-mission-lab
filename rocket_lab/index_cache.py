"""Bounded metadata cache. Changed or atomically replaced files are reread."""
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from .storage import read_json

_entries=OrderedDict()
_lock=RLock()
_bytes=0
MAX_BYTES=4*1024**2
MAX_ENTRIES=2048


def cached_record(path):
    global _bytes
    path=Path(path)
    try:
        # NTFS can preserve timestamps when a same-sized file is atomically
        # replaced rapidly. File identity must also participate in freshness.
        stat=path.stat();stamp=(stat.st_mtime_ns,stat.st_size,stat.st_ino,stat.st_ctime_ns)
    except OSError:return None
    with _lock:
        existing=_entries.get(path)
        if existing and existing[0]==stamp:
            _entries.move_to_end(path)
            return dict(existing[1])
    value=read_json(path)
    if not isinstance(value,dict):return value
    with _lock:
        previous=_entries.pop(path,None)
        if previous:_bytes-=previous[0][1]
        if stat.st_size<=256*1024:
            _entries[path]=(stamp,value);_bytes+=stat.st_size
        while _bytes>MAX_BYTES or len(_entries)>MAX_ENTRIES:
            _,removed=_entries.popitem(last=False);_bytes-=removed[0][1]
    return dict(value)
