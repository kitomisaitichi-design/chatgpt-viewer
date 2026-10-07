"""Durable deletion intent and exporter receipts. Never makes ChatGPT requests."""
import hashlib, json, os, re, shutil, threading, time, uuid
from pathlib import Path
from atomic_files import atomic_bytes

SCHEMA='offline-viewer/delete-v1'
def read(path):
    if not path.exists():return {}
    if path.stat().st_size>2*1024*1024:raise ValueError('Queue metadata is too large')
    return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):atomic_bytes(path,json.dumps(value,ensure_ascii=False).encode(),private=True)
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

class DeletionQueue:
    def __init__(self,archive,files):
        self.archive=archive;self.files=files;self.lock=threading.RLock();self.stop_event=threading.Event();self.worker=None
        with archive.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS deletion_jobs(id TEXT PRIMARY KEY,cid TEXT,scope TEXT,root TEXT,title TEXT,mode TEXT,state TEXT,run TEXT,created REAL,updated REAL,error TEXT,receipt TEXT,UNIQUE(scope,cid))''')
            # A process restart never silently starts a destructive run.
            db.execute("UPDATE deletion_jobs SET state='paused' WHERE state IN ('preparing','waiting','running','retrying')")
        self.control(False)
        # Upgrade existing verified receipts without changing content hashes or organization.
        from remote_state import record
        for row in self.rows():
            if row['state']=='confirmed':record(archive,row['root'],row['cid'],row['scope'],json.loads(row['receipt'] or '{}').get('remote_state','deleted'),'deletion receipt',checked=row['updated'])
        roots=self.roots()
        with archive.connect() as db:manifests=list(db.execute('SELECT cid,manifest,metadata FROM manifest_entries'))
        for item in manifests:
            metadata=json.loads(item['metadata']);root=Path(item['manifest']).parent.resolve()
            if root in roots and metadata.get('deletion_verified') and metadata.get('remote_deleted_at'):
                stamp=metadata['remote_deleted_at'];stamp=stamp/1000 if isinstance(stamp,(float,int)) and stamp>1e11 else stamp
                record(archive,root,item['cid'],roots[root],'deleted','verified exporter index',checked=stamp if isinstance(stamp,(float,int)) else None)
    def chat_account(self,cid):
        if not isinstance(cid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,160}',cid):raise ValueError('Choose a saved ChatGPT conversation')
        roots=self.roots()
        with self.archive.connect() as db:
            options={Path(r[0]).parent.resolve() for r in db.execute('SELECT manifest FROM manifest_entries WHERE cid=?',(cid,))}&roots.keys()
        if len(options)!=1:raise ValueError('Remote actions require one unambiguous exporter account/index')
        root=options.pop();return root,roots[root]
    def check_remote(self,cid):
        root,scope=self.chat_account(cid);bridge=read(root/'.viewer-queue/bridge.json')
        if bridge.get('connection',{}).get('blocked'):return dict(queued=False,blocked=True)
        target=root/'.viewer-queue/checks'/(cid+'.json');old=read(target)
        if old and time.time()-old.get('created',0)<900:return dict(queued=True,id=old['id'])
        value=dict(schema='offline-viewer/status-v1',id=uuid.uuid4().hex,cid=cid,scope=scope,created=time.time())
        write(target,value);self.start();return dict(queued=True,id=value['id'])
    def reconnect(self):
        for root in self.roots():write(root/'.viewer-queue/reconnect.json',dict(nonce=uuid.uuid4().hex,updated=time.time()))
        self.start();return dict(requested=True,message='Reconnecting through the browser worker; allow up to 30 seconds for its wake alarm.')
    def collect_checks(self):
        from remote_state import record
        for root,scope in self.roots().items():
            directory=root/'.viewer-queue/checks'
            if not directory.is_dir():continue
            for path in list(directory.glob('*.json'))[:1000]:
                command=read(path);ident=command.get('id','')
                if not re.fullmatch(r'[a-f0-9]{32}',ident) or command.get('schema')!='offline-viewer/status-v1' or command.get('scope')!=scope:continue
                receipt=read(root/'.viewer-queue/check-receipts'/(ident+'.json'))
                if any(receipt.get(k)!=command.get(k) for k in ('schema','id','cid','scope')) or receipt.get('verified') is not True:continue
                if receipt.get('state') not in ('available','deleted','unavailable'):continue
                with self.archive.connect() as db:old=db.execute('SELECT checked FROM remote_chat_state WHERE root=? AND cid=?',(str(root),command['cid'])).fetchone()
                checked=receipt.get('checked',0)
                if not old or old['checked']<checked:record(self.archive,root,command['cid'],scope,receipt['state'],'authenticated lookup',receipt.get('detail',''),checked=checked)
    def rows(self):
        with self.archive.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM deletion_jobs ORDER BY created,id')]
    def roots(self):
        with self.archive.connect() as db:
            manifests=[Path(r[0]) for r in db.execute('SELECT DISTINCT manifest FROM manifest_entries')]
        result={}
        for manifest in manifests:
            root=manifest.parent.resolve()
            if root in result:continue
            try:
                from exporter_bridge import read_metadata
                metadata=read_metadata(root/'conversation-index.json') or {};scope=metadata.get('scope')
                if isinstance(scope,dict):scope=scope.get('key')
                if scope:result[root]=str(scope)
            except (ValueError,OSError):continue
        return result
    def enqueue(self,ids,mode='library'):
        if mode not in ('library','preserve'):raise ValueError('Choose Library cleanup or preserve local copy')
        if not isinstance(ids,list) or not ids or len(ids)>1000:raise ValueError('Select between 1 and 1000 chats')
        roots=self.roots();catalog={c['id']:c for c in self.archive.catalog()};prepared=[]
        with self.archive.connect() as db:
            for cid in dict.fromkeys(ids):
                c=catalog.get(cid)
                if not c:raise ValueError('Conversation was not found')
                if Path(c['path']).suffix.lower()=='.jsonl' or c['kind']=='codex' and not c.get('url'):raise ValueError('Native Codex sessions support local Trash, not ChatGPT remote deletion')
                options={Path(r[0]).parent.resolve() for r in db.execute('SELECT manifest FROM manifest_entries WHERE cid=?',(cid,))}&roots.keys()
                if len(options)!=1:raise ValueError('Deletion requires one unambiguous exporter account/index for '+c['title'])
                root=options.pop();prepared.append((cid,c,root,roots[root]))
        with self.lock,self.archive.connect() as db:
            for cid,c,root,scope in prepared:
                old=db.execute('SELECT state,mode FROM deletion_jobs WHERE scope=? AND cid=?',(scope,cid)).fetchone()
                if old and old['state']!='cancelled':
                    if old['mode']!=mode:
                        if old['state'] not in ('queued','failed'):raise ValueError('Retention cannot change while this job is active or already complete')
                        db.execute("UPDATE deletion_jobs SET mode=? WHERE scope=? AND cid=?",(mode,scope,cid))
                    continue
                db.execute('INSERT OR REPLACE INTO deletion_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,cid,scope,str(root),c['alias'] or c['title'],mode,'queued','',time.time(),time.time(),'',''))
        return self.status()
    def control(self,enabled,run=None):
        for root in {Path(r['root']) for r in self.rows()}:
            try:
                target=root/'.viewer-queue/control.json';old=read(target)
                write(target,dict(schema=SCHEMA,enabled=bool(enabled),run=run if run is not None else old.get('run',''),updated=time.time()))
            except (OSError,ValueError) as error:
                with self.archive.connect() as db:db.execute("UPDATE deletion_jobs SET state='paused',error=? WHERE root=? AND state NOT IN ('confirmed','cancelled')",('Queue folder unavailable: '+str(error),str(root)))
                if enabled:raise
    def action(self,action,ids=None):
        with self.lock:
            if action=='run':
                rows=[r for r in self.rows() if r['state'] not in ('confirmed','cancelled')]
                if not rows:raise ValueError('The deletion queue is empty')
                if any(r['state'] in ('preparing','waiting','running','retrying') for r in rows):raise ValueError('Queue is already running; pause before reviewing again')
                if set(ids or [])!={r['id'] for r in rows}:raise ValueError('The queue changed. Review all pending chats before running')
                # Backups happen asynchronously before a command becomes executable.
                run=uuid.uuid4().hex
                with self.archive.connect() as db:db.execute("UPDATE deletion_jobs SET state='preparing',run=?,error='' WHERE state NOT IN ('confirmed','cancelled')",(run,))
                self.control(False,run)
            elif action in ('pause','stop'):
                self.control(False)
                with self.archive.connect() as db:db.execute("UPDATE deletion_jobs SET state='paused' WHERE state NOT IN ('confirmed','cancelled','failed')")
            elif action=='remove':
                self.control(False)
                with self.archive.connect() as db:
                    for ident in ids or []:db.execute("UPDATE deletion_jobs SET state='cancelled' WHERE id=? AND state IN ('queued','paused','failed')",(ident,))
            else:raise ValueError('Unknown queue action')
        self.start();return self.status()
    def start(self):
        if self.worker and self.worker.is_alive():return
        self.worker=threading.Thread(target=self.loop,daemon=True);self.worker.start()
    def loop(self):
        while not self.stop_event.is_set():
            try:self.tick()
            except Exception as error:
                with self.archive.connect() as db:db.execute("UPDATE deletion_jobs SET error=? WHERE state IN ('preparing','waiting','running','retrying')",(str(error),))
            self.stop_event.wait(2 if any(r['state'] in ('preparing','waiting','running','retrying') for r in self.rows()) else 10)
    def snapshot(self,row):
        from thread_attachments import thread_markdown
        base=self.archive.data_dir/'deletion-recovery'/row['id'];base.mkdir(parents=True,exist_ok=True)
        text,origin=thread_markdown(self.archive,row['cid'])
        atomic_bytes(base/'conversation.md',text.encode())
        with self.archive.connect() as db:source=db.execute('SELECT path FROM chats WHERE id=? UNION ALL SELECT path FROM manifest_entries WHERE cid=? LIMIT 1',(row['cid'],row['cid'])).fetchone()
        if source:
            path=Path(source['path']);before=path.stat();shutil.copy2(path,base/('source'+path.suffix))
            if (before.st_size,before.st_mtime_ns)!=(path.stat().st_size,path.stat().st_mtime_ns):raise ValueError('Chat changed during backup; retry after the current export finishes')
        self.files.refresh();saved=[]
        with self.files.lock:items=[dict(f) for f in self.files.entries.values() if row['cid'] in f['conversations'] and not f['historical']]
        for f in items:
            path=self.files.available_path(f)
            if not path:continue
            name=hashlib.sha256(str(path).encode()).hexdigest()[:16]+'-'+path.name;target=base/'files'/name;target.parent.mkdir(exist_ok=True)
            before=path.stat();shutil.copy2(path,target);sha=digest(target)
            if digest(path)!=sha or (before.st_size,before.st_mtime_ns)!=(path.stat().st_size,path.stat().st_mtime_ns):raise ValueError('Attachment changed while backing up; no deletion command sent')
            saved.append(dict(path=str(path),copy=str(target),sha256=sha,conversations=f['conversations'],root=str(f['root']),size=before.st_size))
        write(base/'index.json',dict(schema=SCHEMA,cid=row['cid'],scope=row['scope'],markdown_origin=origin,files=saved))
    def tick(self):
        self.collect_checks()
        rows=self.rows();prepared=[]
        for row in rows:
            if row['state']!='preparing':continue
            try:
                self.snapshot(row)
                command={k:row[k] for k in ('id','cid','scope','mode','run','title')};command.update(schema=SCHEMA,created=row['created'])
                with self.archive.connect() as db:
                    metadata=[json.loads(r['metadata']) for r in db.execute('SELECT manifest,metadata FROM manifest_entries WHERE cid=?',(row['cid'],)) if Path(r['manifest']).parent.resolve()==Path(row['root']).resolve()]
                    state=db.execute('SELECT state FROM deletion_jobs WHERE id=?',(row['id'],)).fetchone()
                if not state or state['state']!='preparing':continue
                command['content_hash']=next((m.get('content_hash') for m in metadata if m.get('content_hash')),None)
                write(Path(row['root'])/'.viewer-queue/commands'/(row['id']+'.json'),command)
                with self.archive.connect() as db:db.execute("UPDATE deletion_jobs SET state='waiting',updated=? WHERE id=?",(time.time(),row['id']))
                prepared.append(row)
            except Exception as error:
                with self.archive.connect() as db:db.execute("UPDATE deletion_jobs SET state='failed',error=? WHERE id=?",(str(error),row['id']))
        # No remote operation is permitted until every snapshot in the reviewed run succeeds.
        current=self.rows()
        if not self.stop_event.is_set() and prepared and not any(r['state'] in ('failed','paused','preparing') and r['run']==prepared[0]['run'] for r in current):self.control(True,prepared[0]['run'])
        elif not self.stop_event.is_set() and any(r['state'] in ('waiting','running','retrying') for r in current) and not any(r['state'] in ('failed','paused','preparing') for r in current):self.control(True)
        for row in self.rows():
            if row['state'] not in ('waiting','running','retrying','paused'):continue
            receipt=read(Path(row['root'])/'.viewer-queue/receipts'/(row['id']+'.json'))
            if not receipt:continue
            if any(receipt.get(k)!=row[k] for k in ('id','cid','scope','run')) or receipt.get('schema')!=SCHEMA:continue
            state=receipt.get('state')
            if state not in ('running','retrying','confirmed','failed','paused'):continue
            if state=='confirmed':
                if receipt.get('verified') is not True:continue
                from remote_state import record
                remote=receipt.get('remote_state','deleted')
                if remote not in ('deleted','unavailable'):continue
                record(self.archive,row['root'],row['cid'],row['scope'],remote,'deletion receipt',checked=receipt.get('updated') or time.time())
                if remote=='deleted':self.archive.organize(row['cid'],{'trashed':1})
                if row['mode']=='library' and remote=='deleted':
                    try:self.cleanup(row)
                    except Exception as error:receipt['error']='Remote deletion confirmed; local cleanup needs attention: '+str(error)
            elif row['state']=='paused' and state in ('running','retrying'):continue
            with self.archive.connect() as db:db.execute('UPDATE deletion_jobs SET state=?,updated=?,error=?,receipt=? WHERE id=?',(state,time.time(),receipt.get('error',''),json.dumps(receipt),row['id']))
        # Completed metadata must not exhaust the browser's bounded active inbox.
        for row in self.rows():
            if row['state'] not in ('confirmed','cancelled','failed'):continue
            source=Path(row['root'])/'.viewer-queue/commands'/(row['id']+'.json')
            if source.exists():
                target=Path(row['root'])/'.viewer-queue/history'/row['run']/(row['id']+'.json');target.parent.mkdir(parents=True,exist_ok=True);os.replace(source,target)
    def cleanup(self,row):
        # Only verified, unshared local Library copies are removed. Recovery copies stay available.
        index=read(self.archive.data_dir/'deletion-recovery'/row['id']/'index.json')
        self.files.refresh()
        with self.files.lock:current=[dict(f) for f in self.files.entries.values()]
        for f in index.get('files',[]):
            path=Path(f['path']);copy=Path(f['copy'])
            uses={cid for item in current if item['target']==path for cid in item['conversations']}
            if uses-{row['cid']} or 'library' not in {s for item in current if item['target']==path for s in item['sources']}:continue
            if path.is_file() and path.resolve().is_relative_to(Path(f['root']).resolve()) and digest(path)==f['sha256'] and digest(copy)==f['sha256']:
                # Rename on the same volume instead of unlinking a file that an exporter may replace.
                recovery=Path(f['root'])/'.viewer-queue/recovery'/row['id'];recovery.mkdir(parents=True,exist_ok=True)
                moved=recovery/(hashlib.sha256(str(path).encode()).hexdigest()[:16]+'-'+path.name)
                os.replace(path,moved)
                if digest(moved)!=f['sha256']:
                    if not path.exists():os.replace(moved,path)
                    raise ValueError('A Library file changed during cleanup; its bytes were retained for recovery')
    def status(self):
        rows=self.rows();bridges=[]
        for root,scope in self.roots().items():
            bridge=read(root/'.viewer-queue/bridge.json')
            reset=read(root/'.viewer-queue/reconnect.json');connection=bridge.get('connection',{}) if bridge.get('scope')==scope else {}
            bridges.append(dict(root=str(root),scope=scope,connected=bridge.get('connected') is True and bridge.get('scope')==scope and time.time()-bridge.get('updated',0)<45,version=bridge.get('version',''),error=bridge.get('error',''),connection=connection,reconnecting=bool(reset.get('nonce') and connection.get('nonce')!=reset['nonce'] and time.time()-reset.get('updated',0)<90),fresh=time.time()-bridge.get('updated',0)<45))
        jobs=[dict({k:v for k,v in r.items() if k!='receipt'},remote_state=json.loads(r['receipt'] or '{}').get('remote_state','')) for r in rows]
        return dict(jobs=jobs,bridges=bridges,adapter_folder=self.archive.settings().get('exporterBridgeFolder',''))
    def close(self):
        self.stop_event.set();self.control(False)
        if self.worker and self.worker is not threading.current_thread():self.worker.join(timeout=3)
        self.control(False)
