"""Bounded wait for Windows checkpoint replace contention; never tool replay.

No ACL/attribute changes. Source and destination must remain exactly unchanged
after a failed replace. Non-Windows and all other failures propagate immediately.
"""
import hashlib,os,time
from pathlib import Path
def fingerprint(path):
    path=Path(path)
    if path.is_symlink():raise RuntimeError('Symlink checkpoint replace prohibited')
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def replace_checkpoint(tmp,path,*,platform_name=None,attempts=6):
    tmp=Path(tmp);path=Path(path)
    if tmp.parent!=path.parent or not tmp.is_file() or not 1<=attempts<=6:raise RuntimeError('Invalid bounded same-directory checkpoint replace')
    source=fingerprint(tmp);destination=fingerprint(path);platform_name=os.name if platform_name is None else platform_name
    for attempt in range(attempts):
        try:return os.replace(tmp,path)
        except PermissionError as exc:
            if platform_name!='nt' or getattr(exc,'winerror',None) not in (5,32,33) or attempt+1==attempts:raise
            if not tmp.is_file() or fingerprint(tmp)!=source or fingerprint(path)!=destination:raise RuntimeError('Checkpoint changed after failed replace; no retry') from exc
            time.sleep(0.02*(2**attempt))
