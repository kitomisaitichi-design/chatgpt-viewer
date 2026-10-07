"""Local Codex discovery. Read metadata only; load conversation bodies on demand."""
import json, os, re, sqlite3, threading, time, urllib.parse
from contextlib import closing
from pathlib import Path

def homes():
    candidates=[configured_home()]
    if os.environ.get('CODEX_HOME'):candidates.append(Path.home()/'.codex')
    return list(dict.fromkeys(p.resolve() for p in candidates if p.is_dir()))

def configured_home():
    value=os.environ.get('CODEX_HOME')
    return (Path(value).expanduser() if value else Path.home()/'.codex').resolve()

def session_header(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        # The producer's first record identifies the format. Never infer it from a filename.
        line=stream.readline(1024*1024)
    record=json.loads(line)
    value=record.get('payload') or {}
    if record.get('type')!='session_meta' or not value.get('id'):
        raise ValueError('Not a native Codex session')
    if not (str(value.get('originator','')).startswith('codex') or value.get('cli_version')):
        raise ValueError('Session has no Codex producer metadata')
    return value

def local_references(raw):
    refs=set()
    for message in raw.get('messages',[]):
        for part in message.get('content',{}).get('parts',[]):
            if isinstance(part,dict):
                value=part.get('asset_pointer') or part.get('path') or part.get('image_url')
                if isinstance(value,str):refs.add(value)
            elif isinstance(part,str):
                refs.update(m[1] or m[2] for m in re.finditer(r'!?\[[^\]\n]*\]\((?:<([^>]+)>|([^\s)]+))\)',part))
    return refs

def reference_path(value):
    if value.lower().startswith('file:'):
        url=urllib.parse.urlsplit(value)
        if url.netloc not in ('','localhost'):raise ValueError('Network paths are not local attachments')
        value=urllib.parse.unquote(url.path)
        if re.match(r'^/[a-zA-Z]:/',value):value=value[1:]
    if value.startswith(('\\\\','//')):raise ValueError('Network paths are not local attachments')
    if re.match(r'^[a-zA-Z][\w+.-]*:',value) and not re.match(r'^[a-zA-Z]:[/\\]',value):raise ValueError('Unsupported attachment URL')
    return Path(urllib.parse.unquote(value)).expanduser()

class NativeCodex:
    def __init__(self,archive):
        self.archive=archive;self.lock=threading.Lock();self.worker=None
        self.session_lock=threading.RLock()
        self.state=dict(running=False,found=0,errors=[],roots=[])
        from native_deletion import NativeDeletionQueue
        self.deletion_queue=NativeDeletionQueue(archive,session_lock=self.session_lock)
    def status(self):
        with self.lock:return dict(self.state,errors=list(self.state['errors']))
    def start(self):
        self.deletion_queue.start()
        with self.lock:
            if self.state['running']:return self.status_unlocked()
            self.state=dict(running=True,found=0,errors=[],roots=[str(p) for p in homes()])
            self.worker=threading.Thread(target=self.discover,daemon=True);self.worker.start()
            return self.status_unlocked()
    def status_unlocked(self):return dict(self.state)
    def discover(self):
        a=self.archive
        try:
            excluded_value=a.settings().get('nativeCodexExcludedSessions',[])
            excluded={str(cid) for cid in excluded_value} if isinstance(excluded_value,list) else set()
            for home in homes():
                titles={}
                for dbpath in sorted(home.glob('state_*.sqlite'),reverse=True)[:1]:
                    with closing(sqlite3.connect('file:'+dbpath.as_posix()+'?mode=ro',uri=True,timeout=1)) as db:
                        columns={r[1] for r in db.execute('PRAGMA table_info(threads)')}
                        if {'id','title','rollout_path'}<=columns:
                            titles={r[0]:(r[1],r[2]) for r in db.execute('SELECT id,title,rollout_path FROM threads')}
                for name in ('sessions','archived_sessions'):
                    root=home/name
                    if not root.is_dir():continue
                    for base,dirs,files in os.walk(root,followlinks=False):
                        dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()]
                        for filename in files:
                            if a.cache_stop.is_set():return
                            path=Path(base)/filename
                            if path.suffix!='.jsonl' or path.is_symlink():continue
                            try:
                                metadata=session_header(path);cid=str(metadata['id'])
                                if cid in excluded:continue
                                title=titles.get(cid)
                                # A state row must point at this exact session before its title is trusted.
                                if title and Path(title[1]).resolve()==path.resolve():metadata['title']=title[0]
                                entry=dict(id=cid,title=metadata.get('title') or path.stem,url='',json=str(path.relative_to(root)),chat_kind='codex',create_time=metadata.get('timestamp'),update_time=path.stat().st_mtime)
                                with self.session_lock:
                                    with a.lock:
                                        current=a.settings().get('nativeCodexExcludedSessions',[])
                                        if isinstance(current,list) and cid in {str(value) for value in current}:continue
                                        a.register_manifest(entry,root/'native-codex-index.json',root)
                                    a.publish_sources([a.live_sources[cid]] if cid in a.live_sources else [])
                                with self.lock:self.state['found']+=1
                            except (ValueError,OSError) as error:
                                with self.lock:
                                    if len(self.state['errors'])<8:self.state['errors'].append(filename+': '+str(error))
                        time.sleep(.002)
        except Exception as error:
            with self.lock:self.state['errors'].append(str(error))
        finally:
            with self.lock:self.state['running']=False

    def close(self):
        self.deletion_queue.close()
