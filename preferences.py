"""Version-independent user preferences; caches and Google credentials stay local."""
import json, os, time
from contextlib import contextmanager
from pathlib import Path
from atomic_files import atomic_bytes

FIELDS = ('category', 'pinned', 'position', 'alias', 'trashed', 'color', 'sticky')

def profile_path():
    base = Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'.local/share'))
    return base/'OfflineChatViewer'/'preferences.json'

class Preferences:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent/(self.path.name+'.lock')).open('a+b') as lock:
            lock.seek(0, 2)
            if not lock.tell(): lock.write(b'0'); lock.flush()
            lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                for attempt in range(100):
                    try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1); break
                    except OSError:
                        if attempt == 99: raise
                        time.sleep(.02)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            try: yield
            finally:
                lock.seek(0)
                if os.name == 'nt': msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else: fcntl.flock(lock, fcntl.LOCK_UN)

    def read(self):
        if not self.path.exists(): return {}
        value = json.loads(self.path.read_text(encoding='utf-8'))
        if value.get('schema') != 'offline-chat-viewer/preferences-v1':
            raise ValueError('Unrecognized shared preferences. The existing file has been kept.')
        return value

    def update(self, settings=None, organization=None, backup=None):
        with self.locked():
            value = self.read() or dict(schema='offline-chat-viewer/preferences-v1')
            if settings is not None:
                value.setdefault('settings', {}).update({k:v for k,v in settings.items() if k not in ('typeRepairVersion', 'steadySidebarPolicy')})
            if organization is not None:
                rows = value.setdefault('organization', {})
                for row in organization:
                    rows.setdefault(row['id'], {}).update({k:row[k] for k in FIELDS if k in row})
            if backup is not None: value.setdefault('backup', {}).update(backup)
            value['updated'] = time.time()
            atomic_bytes(self.path, json.dumps(value, ensure_ascii=False, indent=2).encode(), private=True)
            return value

def attach(archive, path):
    profile = Preferences(path)
    saved = profile.read()
    if saved:
        archive.save_settings(saved.get('settings', {}))
        archive.organize_many([dict(id=cid, **row) for cid,row in saved.get('organization', {}).items()])
        if saved.get('backup'):
            config = archive.data_dir/'backup-config.json'
            local = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
            local.update(saved['backup'])
            atomic_bytes(config, json.dumps(local, indent=2).encode())
    else:
        with archive.connect() as db:
            rows = [dict(id=r['cid'], **{k:r[k] for k in FIELDS}) for r in db.execute('SELECT * FROM organization')]
        config = archive.data_dir/'backup-config.json'
        backup = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        profile.update(archive.settings(), rows, backup)
    archive.profile = profile
    return profile
