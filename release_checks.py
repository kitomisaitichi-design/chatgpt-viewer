"""Bounded public release checks, independent of chat scans and backup jobs."""
import json,re,threading,time,urllib.request
from atomic_files import atomic_bytes
API='https://api.github.com/repos/kitomisaitichi-design/chatgpt-viewer/releases/latest'
PAGE='https://github.com/kitomisaitichi-design/chatgpt-viewer/releases/latest'
def interval(value):
    return value if type(value) is int and value in (0,12,24,168) else 24

def version(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',str(value))
    if not match:raise ValueError('Unexpected release version')
    return tuple(map(int,match.groups()))

def request_release():
    request=urllib.request.Request(API,headers={'Accept':'application/vnd.github+json','User-Agent':'Offline-Chat-Viewer-Release-Check'})
    with urllib.request.urlopen(request,timeout=15) as response:
        data=response.read(512*1024+1)
    if len(data)>512*1024:raise ValueError('Release metadata exceeds the size limit')
    return json.loads(data)

class ReleaseChecks:
    def __init__(self,archive,current,fetch=request_release,clock=time.time):
        self.archive=archive;self.current=current;self.fetch=fetch;self.clock=clock
        self.path=archive.data_dir/'release-check.json';self.state={};self.lock=threading.RLock();self.wake=threading.Event();self.stop=threading.Event();self.thread=None;self.checking=False;self.worker=None
        try:
            if self.path.exists():
                self.state=json.loads(self.path.read_text(encoding='utf8'))
                if not isinstance(self.state,dict):raise ValueError('Invalid saved status')
                if self.state.get('version'):version(self.state['version'])
        except (OSError,ValueError) as e:self.state={'error':'Could not read previous release check: '+str(e)}
    def status(self):
        with self.lock:
            hours=interval(self.archive.settings().get('releaseCheckHours',24));last=self.state.get('checkedAt',0)
            state=dict(self.state)
            if not (self.archive.data_dir/'pending-update.json').exists():state.pop('stagedVersion',None)
            return dict(state,hours=hours,checking=self.checking,current=self.current,url=PAGE,available=bool(self.state.get('version') and version(self.state['version'])>version(self.current)),nextCheckAt=(last+hours*3600 if last else self.clock()) if hours else None)
    def check(self):
        with self.lock:
            if self.checking:return self.status()
            self.checking=True
            self.worker=threading.Thread(target=self._check,daemon=True,name='viewer-release-check');self.worker.start()
            return self.status()
    def _check(self):
        try:
            release=self.fetch()
            if not isinstance(release,dict) or release.get('draft') or release.get('prerelease'):raise ValueError('Unexpected release metadata')
            tag=release.get('tag_name');version(tag)
            result={'version':tag.removeprefix('v'),'error':''}
            if version(tag)>version(self.current) and self.archive.settings().get('silentUpdates',False):
                import os
                if os.name!='nt':raise ValueError('Silent installation is supported by the Windows launcher only')
                from silent_update import stage_release
                if stage_release(self.archive,release,lock=self.lock):result['stagedVersion']=tag.removeprefix('v')
        except Exception as e:result={'error':str(e)}
        with self.lock:
            self.state.update(result,checkedAt=self.clock())
            try:atomic_bytes(self.path,json.dumps(self.state).encode(),private=True)
            except OSError as e:self.state['error']='Could not save release-check status: '+str(e)
            finally:self.checking=False;self.wake.set()
    def reschedule(self):
        with self.lock:
            if not self.archive.settings().get('silentUpdates',False):
                (self.archive.data_dir/'pending-update.json').unlink(missing_ok=True)
        self.wake.set()
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self._run,daemon=True,name='viewer-release-schedule');self.thread.start()
    def _run(self):
        while not self.stop.is_set():
            self.wake.clear();s=self.status();due=s['nextCheckAt']
            if due is not None and not s['checking'] and due<=self.clock():self.check();continue
            delay=None if due is None or s['checking'] else max(1,due-self.clock())
            self.wake.wait(delay)
    def close(self):
        self.stop.set();self.wake.set()
        if self.thread:self.thread.join(timeout=2)
