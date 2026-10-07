"""Bounded cross-process intents. Claim/ack survives a viewer or idle-job restart."""
import json,threading,time
from contextlib import contextmanager
from pathlib import Path
from atomic_files import atomic_bytes

class BackupQueue:
    def __init__(self,path,lock):
        self.path=Path(path);self.lock=lock;self.guard=threading.RLock()
    @contextmanager
    def locked(self):
        with self.guard:
            for attempt in range(100):
                context=self.lock(self.path.with_suffix('.queue.lock'))
                try:context.__enter__();break
                except ValueError:
                    if attempt==99:raise
                    time.sleep(.02)
            try:yield
            finally:context.__exit__(None,None,None)
    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'pending':[]}
    def write(self,state):atomic_bytes(self.path,json.dumps(state).encode(),private=True)
    def push(self,kind,upload=True,scheduled=False):
        with self.locked():
            state=self.read();pending=state.setdefault('pending',[])
            job=next((j for j in pending if j['kind']==kind and j['upload']==bool(upload)),None)
            if job:
                job['scheduled']&=bool(scheduled)
                if not scheduled:job['at']=time.time()
            else:pending.append(dict(kind=kind,upload=bool(upload),scheduled=bool(scheduled),at=time.time()))
            self.write(state)
    def claim(self,eligible):
        with self.locked():
            state=self.read();job=state.get('active')
            if job and eligible(job):return job
            pending=state.setdefault('pending',[])
            if job:
                state.pop('active',None)
                old=next((j for j in pending if j['kind']==job['kind'] and j['upload']==job['upload']),None)
                if old:old['scheduled']&=job['scheduled']
                else:pending.insert(0,job)
                self.write(state)
            for index,job in enumerate(pending):
                if eligible(job):
                    state['active']=pending.pop(index);self.write(state);return job
    def ack(self):
        with self.locked():
            state=self.read();state.pop('active',None);self.write(state)
    def clear(self):
        with self.locked():
            state=self.read();state['pending']=[];state.pop('active',None);state['cancel_at']=time.time();self.write(state)
    def cancelled(self,job):return self.read().get('cancel_at',0)>=job.get('at',0)
    def status(self):
        with self.locked():
            state=self.read();return dict(pending=len(state.get('pending',[])),active=bool(state.get('active')))
