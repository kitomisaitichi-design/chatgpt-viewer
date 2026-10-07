"""Resumable per-file capture. Packaging never rereads the live exporter."""
import hashlib,json,os,shutil,time
from pathlib import Path
from atomic_files import atomic_bytes

class SnapshotPending(Exception):
    """A source is still changing; retain the queue claim and verified captures."""

class BackupSourceChanged(ValueError):
    def __init__(self,path,message):self.path=path;super().__init__(message)

class Snapshot:
    def __init__(self,folder,root,key,progress,check):
        self.folder=Path(folder);self.root=Path(root).resolve();self.progress=progress;self.check=check
        self.folder.mkdir(parents=True,exist_ok=True);self.tree=self.folder/'files';self.tree.mkdir(exist_ok=True)
        self.index=self.folder/'capture.json';self.last_save=time.monotonic()
        self.state=json.loads(self.index.read_text(encoding='utf-8')) if self.index.exists() else {}
        if self.state.get('root')!=str(self.root):
            # Distinct source trees get distinct folders from the manager.
            if self.state:raise ValueError('Snapshot source changed unexpectedly.')
            self.state={'root':str(self.root),'files':{}}
        if self.state.get('key')!=key:
            self.state.update(key=key,started=time.time());self.state.pop('documents',None);self.state.pop('candidates',None)
        self.save()
    def save(self):
        atomic_bytes(self.index,json.dumps(self.state,separators=(',',':')).encode(),private=True);self.last_save=time.monotonic()
    def relative(self,path):
        path=Path(path)
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():raise ValueError('Unsafe snapshot source: '+str(path))
        return path.relative_to(self.root).as_posix()
    def paths(self,kind,paths):
        if kind not in self.state:
            self.state[kind]=sorted(self.relative(p) for p in paths);self.save()
        return [self.root/p for p in self.state[kind]]
    def exists(self,path):
        relative=self.relative(path);old=self.state['files'].get(relative,{})
        return old.get('key')==self.state['key'] and (self.tree/relative).is_file()
    def capture(self,path):
        self.check();relative=self.relative(path);target=self.tree/relative;old=self.state['files'].get(relative,{})
        staged=target.stat() if target.is_file() else None
        verified=staged and [staged.st_size,staged.st_mtime_ns]==old.get('staged')
        if verified and old.get('key')==self.state['key']:return target,old['file']
        try:before=path.stat()
        except FileNotFoundError:raise SnapshotPending(relative+' is temporarily unavailable.') from None
        signature=[before.st_size,before.st_mtime_ns,before.st_ctime_ns]
        if verified and old.get('source')==signature:
            old['key']=self.state['key'];return target,old['file']
        target.parent.mkdir(parents=True,exist_ok=True)
        # Bounded immediate attempts; unstable files yield to a durable background retry.
        for attempt in range(2):
            self.check();temporary=target.with_name('.'+target.name+'.capture-partial')
            try:
                before=path.stat();signature=[before.st_size,before.st_mtime_ns,before.st_ctime_ns]
                if shutil.disk_usage(self.folder).free<before.st_size+128*1024**2:raise ValueError('Not enough space for a verified backup snapshot. Free space and retry; completed ZIPs are kept.')
                sha=hashlib.sha256();size=0;remaining=before.st_size
                with path.open('rb') as source,temporary.open('wb') as sink:
                    while remaining:
                        part=source.read(min(1024*1024,remaining))
                        if not part:break
                        self.check();sink.write(part);sha.update(part);size+=len(part)
                        remaining-=len(part)
                        self.progress(phase='Capturing backup snapshot',current=relative,done=size,total=before.st_size)
                    opened=os.fstat(source.fileno())
                after=path.stat()
                if signature!=[after.st_size,after.st_mtime_ns,after.st_ctime_ns] or (opened.st_dev,opened.st_ino)!=(before.st_dev,before.st_ino) or (after.st_dev,after.st_ino)!=(before.st_dev,before.st_ino) or (opened.st_size,opened.st_mtime_ns)!=(before.st_size,before.st_mtime_ns) or size!=before.st_size:continue
                os.utime(temporary,ns=(before.st_atime_ns,before.st_mtime_ns));os.replace(temporary,target)
                staged=target.stat();value=dict(size=size,mtime_ns=before.st_mtime_ns,sha256=sha.hexdigest())
                self.state['files'][relative]=dict(key=self.state['key'],source=signature,staged=[staged.st_size,staged.st_mtime_ns],file=value)
                if time.monotonic()-self.last_save>=1:self.save()
                return target,value
            except FileNotFoundError:continue
            finally:
                if temporary.exists():temporary.unlink()
        raise SnapshotPending(relative+' is still being saved by the exporter.')
    def capture_many(self,paths):
        pending=[]
        try:
            for number,path in enumerate(paths):
                try:self.capture(path)
                except SnapshotPending as error:pending.append(str(error))
                if number%64==63:self.save()
        finally:self.save()
        if pending:raise SnapshotPending(str(len(pending))+' changing file(s); '+pending[0])
    def prune(self,files):
        """Discard obsolete disposable captures only after completed ZIPs are saved."""
        for relative in list(self.state['files']):
            if relative in files:continue
            target=self.tree/relative
            if not target.resolve().is_relative_to(self.tree.resolve()) or target.is_symlink():raise ValueError('Unsafe cached snapshot path.')
            target.unlink(missing_ok=True);self.state['files'].pop(relative)
        self.save()
    def invalidate(self,relative):
        self.state['files'].pop(relative,None);self.save()
