"""Atomic state writes that tolerate brief Windows reader/antivirus locks."""
import os,tempfile,time
from pathlib import Path

def atomic_bytes(path,content,private=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent);temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(content);stream.flush()
        if private:os.chmod(temporary,0o600)
        for attempt in range(12):
            try:os.replace(temporary,path);return
            except OSError as error:
                if not isinstance(error,PermissionError) and getattr(error,'winerror',None) not in (5,32,33):raise
                if attempt==11:raise PermissionError('Windows is holding '+path.name+'. Close any app locking this file, then retry. Your completed ZIPs are kept.') from error
                time.sleep(min(.02*2**attempt,.15))
    finally:
        if temporary.exists():temporary.unlink()
