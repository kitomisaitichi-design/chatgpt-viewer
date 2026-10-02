"""Scheduling and conservative retention for viewer-owned backup slots."""
import ctypes, json, os, zipfile
from pathlib import Path

def interval_seconds(config):
    hours=168 if config.get('cadence')=='weekly' else 24 if config.get('cadence')=='daily' else config.get('interval_hours',24)
    return max(1, min(168, int(hours)))*3600

def power_allowed(config):
    if not config.get('ac_only', True) or os.name != 'nt': return True
    class Power(ctypes.Structure):
        _fields_=[('ac',ctypes.c_ubyte),('flags',ctypes.c_ubyte),('percent',ctypes.c_ubyte),('reserved',ctypes.c_ubyte),('life',ctypes.c_uint32),('full',ctypes.c_uint32)]
    status=Power()
    return bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))) and status.ac==1

def identical(left,right):
    if left.stat().st_size!=right.stat().st_size:return False
    with left.open('rb') as a,right.open('rb') as b:
        while True:
            part=a.read(1024*1024)
            if part!=b.read(1024*1024):return False
            if not part:return True

def retire_extras(folder, modes, owned_paths=()):
    """Keep requested stable slots. Retire extra viewer ZIPs, never unrelated ZIPs."""
    folder=Path(folder).resolve();keep={'Chat-Archive-'+mode.title()+'.zip' for mode in modes};moved=[]
    if not folder.is_dir(): return moved
    owned={str(Path(p).resolve()) for p in owned_paths if p}
    for candidate in folder.glob('Chat-Archive-*.zip'):
        if candidate.name in keep or candidate.is_symlink() or not candidate.is_file(): continue
        known=str(candidate.resolve()) in owned
        if not known:
            try:
                with zipfile.ZipFile(candidate) as z:
                    info=z.getinfo('backup-manifest.json')
                    known=info.file_size<2*1024*1024 and json.loads(z.read(info)).get('schema')=='offline-chat-viewer/backup-v1'
            except (OSError,ValueError,KeyError,zipfile.BadZipFile): continue
        if not known: continue
        duplicate=next((folder/name for name in keep if (folder/name).is_file() and not (folder/name).is_symlink() and identical(candidate,folder/name)),None)
        if duplicate:
            candidate.unlink();moved.append('deduplicated:'+str(candidate));continue
        retired=folder/'.retired-viewer-backups';retired.mkdir(exist_ok=True)
        target=retired/candidate.name
        # Preserve distinct historical data for recovery; exact duplicate names use a unique suffix.
        if target.exists():
            import uuid
            target=retired/(candidate.stem+'-'+uuid.uuid4().hex[:8]+'.zip')
        candidate.replace(target);moved.append(str(target))
    return moved
