"""Deterministic export backups, linked local assets, safe ZIP imports and idle jobs."""
import ctypes,datetime,hashlib,json,os,re,shutil,stat,subprocess,threading,time,urllib.parse,uuid,zipfile
from pathlib import Path,PurePosixPath
from contextlib import contextmanager
from drive_backup import Drive,read_private,save_private
from discovery import scan_boundary
from export_bundle import documents as discover_documents,asset_paths,counts,conversation_map,progress_files,linked_index
from atomic_files import atomic_bytes
from folder_tools import drive_suggestion,open_folder
from backup_policy import interval_seconds,power_allowed,retire_extras
from exporter_bridge import metadata_sources,timestamp

SKIP={'.viewer-data','.git','__pycache__','node_modules','runtime','models','.semantic-env'}
TEXT={'.md','.json','.jsonl'}

def write_json(path,value):
    atomic_bytes(path,json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8'))

def digest(path,check=lambda:None):
    sha=hashlib.sha256();md5=hashlib.md5()
    with Path(path).open('rb') as source:
        while part:=source.read(1024*1024):check();sha.update(part);md5.update(part)
    return sha.hexdigest(),md5.hexdigest()

def idle_seconds():
    if os.name!='nt':return None
    class Input(ctypes.Structure):_fields_=[('size',ctypes.c_uint),('tick',ctypes.c_uint)]
    value=Input(ctypes.sizeof(Input),0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(value)):return None
    return ((ctypes.windll.kernel32.GetTickCount()-value.tick)&0xffffffff)/1000

@contextmanager
def job_lock(path):
    lock=Path(path).open('a+b');lock.seek(0,2)
    if not lock.tell():lock.write(b'0');lock.flush()
    lock.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise ValueError('A backup or import is already running.') from None
        else:
            import fcntl
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise ValueError('A backup or import is already running.') from None
        yield
    finally:lock.close()

def local_links(text):
    values=[]
    # Scan the closing label marker; unmatched '[' in saved code must stay linear.
    for match in re.finditer(r'\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+[^)\n]*)?\)',text):values.append(match[1].strip('<>'))
    for match in re.finditer(r'(?:src|href)=["\']([^"\']+)["\']',text,re.I):values.append(match[1])
    for match in re.finditer(r'"(?:[\w-]{0,64}(?:path|filename|file_name|url|asset_pointer))"\s*:\s*("(?:\\.|[^"\\])*")',text,re.I):
        try:values.append(json.loads(match[1]))
        except ValueError:pass
    for match in re.finditer(r'"((?:\.\.?[/\\]|attachments[/\\]|images[/\\]|files[/\\]|downloads[/\\])(?:\\.|[^"\\])*)"',text):
        try:values.append(json.loads('"'+match[1]+'"'))
        except ValueError:pass
    return {urllib.parse.unquote(value.split('#')[0].split('?')[0]).replace('\\','/') for value in values if isinstance(value,str) and value and not re.match(r'^(?:https?:|data:|mailto:|javascript:|#)',value,re.I)}

def plan_files(root,cache=None,progress=lambda **kw:None,check=lambda:None,documents=None,exclude=(),links=None,reference_cache=None):
    root=Path(root).expanduser().resolve()
    if not root.is_dir() or root.parent==root:raise ValueError('Choose a specific export folder, not a whole drive.')
    cache=cache or {};missing=[];links={} if links is None else links
    if documents is None:documents=discover_documents(root,root,threading.Event(),Path(__file__).parent,exclude)
    paths=set(documents);reference_cache={} if reference_cache is None else reference_cache
    # Keep paths relative to the export root, so Markdown/JSON links survive extraction.
    for index,p in enumerate(documents):
        check();progress(phase='Finding linked attachments',done=index+1,total=len(documents),current=p.name)
        if p.stat().st_size>512*1024*1024:raise ValueError(p.name+' is over 512 MiB. Split that export before backing it up.')
        relative=p.relative_to(root).as_posix();stat=p.stat();saved=reference_cache.get(relative,{})
        if saved.get('size')==stat.st_size and saved.get('mtime_ns')==stat.st_mtime_ns and 'refs' in saved:refs=set(saved['refs'])
        else:
            refs=set();tail=''
            with p.open(encoding='utf-8-sig',errors='replace') as source:
                while part:=source.read(1024*1024):
                    check();text=tail+part;refs.update(local_links(text));tail=text[-16384:]
            reference_cache[relative]=dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns,refs=sorted(refs))
        for ref in refs:
            target=(p.parent/ref).resolve()
            if not target.is_relative_to(root):missing.append(dict(document=p.relative_to(root).as_posix(),reference=ref,reason='Outside the chosen export folder'));continue
            if any(target.is_relative_to(Path(x).resolve()) for x in exclude):continue
            if target.is_file() and not target.is_symlink():paths.add(target);links.setdefault(p.relative_to(root).as_posix(),[]).append(target.relative_to(root).as_posix())
            elif not ref.startswith(('sandbox:','sediment:','file-service:')):missing.append(dict(document=p.relative_to(root).as_posix(),reference=ref,reason='Not saved locally'))
    # Exporters sometimes keep binary attachments by ID without a resolvable text link.
    paths.update(asset_paths(root,documents,check,exclude))
    result={};total=len(paths)
    for index,p in enumerate(sorted(paths)):
        check();relative=p.relative_to(root).as_posix();s=p.stat();old=cache.get(relative,{})
        progress(phase='Checking backup changes',done=index+1,total=total,current=p.name)
        sha=old.get('sha256') if old.get('sha256') and old.get('size')==s.st_size and old.get('mtime_ns')==s.st_mtime_ns else digest(p,check)[0]
        after=p.stat()
        if (s.st_size,s.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError(p.name+' changed during backup. Retry after the export finishes saving.')
        result[relative]=dict(size=s.st_size,mtime_ns=s.st_mtime_ns,sha256=sha)
    fingerprint=hashlib.sha256(json.dumps([(k,v['sha256']) for k,v in sorted(result.items())],separators=(',',':')).encode()).hexdigest()
    return result,fingerprint,missing

def build_zip(root,destination,files,manifest,settings=None,progress=lambda **kw:None,check=lambda:None,index=None):
    destination=Path(destination);temporary=destination.with_suffix('.zip.partial');root=Path(root).resolve();total=sum(v['size'] for v in files.values());done=0
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
        for relative,expected in sorted(files.items()):
            check();p=root/relative;before=p.stat()
            if before.st_size!=expected['size'] or before.st_mtime_ns!=expected['mtime_ns']:raise ValueError(relative+' changed before packaging. Retry when the export is stable.')
            info=zipfile.ZipInfo('archive/'+relative,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            if hasattr(info,'compress_level'):info.compress_level=3
            else:info._compresslevel=3  # Python 3.10–3.12 expose only the underlying slot.
            info.external_attr=0o100600<<16;sha=hashlib.sha256()
            with p.open('rb') as source,z.open(info,'w',force_zip64=True) as target:
                while part:=source.read(1024*1024):
                    check();target.write(part);sha.update(part);done+=len(part);progress(phase='Packaging '+manifest['mode']+' backup',done=done,total=total,current=p.name)
            if sha.hexdigest()!=expected['sha256']:raise ValueError(relative+' changed during packaging. The previous backup has been kept.')
        for name,value in [('backup-manifest.json',manifest),('viewer-settings.json',settings)]:
            if value is not None:
                info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')))
        if index:
            for name,value in [('archive-index.json',json.dumps(index[0],ensure_ascii=False,sort_keys=True,separators=(',',':'))),('OPEN-ARCHIVE.html',index[1])]:
                info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,value)
    check();os.replace(temporary,destination)
    return digest(destination,check)

def extract_zip(path,destination,progress=lambda **kw:None,check=lambda:None):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(path) as z:
        items=z.infolist()
        if len(items)>100000 or sum(i.file_size for i in items)>20*1024**3:raise ValueError('Archive exceeds the import limit of 100,000 files or 20 GB.')
        seen=set()
        for i in items:
            name=i.filename.replace('\\','/');parts=PurePosixPath(name).parts
            if name.startswith('/') or '..' in parts or any(':' in part or part.endswith((' ','.')) or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part,re.I) for part in parts) or stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unsafe archive path: '+name)
            key=name.casefold()
            if key in seen:raise ValueError('Archive contains duplicate paths: '+name)
            seen.add(key)
            if not (destination/name).resolve().is_relative_to(destination):raise ValueError('Archive path escaped the import folder.')
        for index,i in enumerate(items):
            check();name=i.filename.replace('\\','/');target=destination/name
            if i.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(i) as source,target.open('wb') as sink:
                while part:=source.read(1024*1024):check();sink.write(part)
            saved_time=datetime.datetime(*i.date_time).timestamp();os.utime(target,(saved_time,saved_time))
            progress(phase='Unpacking archive',done=index+1,total=len(items),current=target.name)
    metadata=destination/'backup-manifest.json'
    if metadata.exists():
        manifest=json.loads(metadata.read_text(encoding='utf-8'))
        if manifest.get('schema')=='offline-chat-viewer/backup-v1':
            for relative,value in manifest.get('files',{}).items():
                check();target=(destination/'archive'/relative).resolve()
                if not target.is_relative_to((destination/'archive').resolve()) or not target.is_file():raise ValueError('The backup manifest references an unsafe or missing file.')
                if digest(target,check)[0]!=value.get('sha256'):raise ValueError('A saved file does not match its backup hash: '+relative)
                ns=int(value.get('mtime_ns',0))
                if ns>0:os.utime(target,ns=(ns,ns))
    return destination

class BackupManager:
    def __init__(self,archive,app):
        self.archive=archive;self.app=Path(app);self.data=archive.data_dir;self.folder=self.data/'backups';self.folder.mkdir(exist_ok=True);self.drive=Drive(self.data)
        self.cancel=threading.Event();self.worker=None;self.stop=threading.Event();self.scheduled=False;self.last_write=0;self.progress_lock=threading.RLock()
        self.config_path=self.data/'backup-config.json';self.state_path=self.data/'backup-state.secure';self.status_path=self.data/'backup-progress.json'
        self.lock_path=self.data/'backup.lock'
        if archive.profile:
            self.lock_path=archive.profile.path.with_suffix('.backup.lock')
            shared=archive.profile.path.with_suffix('.backup-state.secure')
            if not shared.exists() and self.state_path.exists():
                with job_lock(self.lock_path):
                    if not shared.exists():atomic_bytes(shared,self.state_path.read_bytes(),private=True)
            self.state_path=shared
        self.folder=Path(self.config()['local_folder']);self.folder.mkdir(parents=True,exist_ok=True)
    def config(self):
        settings=self.archive.settings();default=dict(source=settings.get('scan_start',''),up=settings.get('scan_up',0),source_mode='loader',route='desktop',local_folder=str(self.data.resolve().parent/'Backups'),sync_folder='',enabled=False,cadence='daily',interval_hours=24,idle_minutes=10,idle_required=True,ac_only=True,auto_upload=True,cleanup_extras=True,modes='both',folder_id='',folder_name='')
        if self.config_path.exists():
            saved=json.loads(self.config_path.read_text(encoding='utf-8'));default.update(saved)
            if 'interval_hours' not in saved:default['interval_hours']=168 if saved.get('cadence')=='weekly' else 24
            if 'source_mode' not in saved:default['source_mode']='loader' if saved.get('source')==settings.get('scan_start') else 'custom'
            if 'route' not in saved and saved.get('folder_id'):default['route']='api'
        if default['source_mode']=='loader':default.update(source=settings.get('scan_start',''),up=settings.get('scan_up',0))
        if default['route']=='desktop' and not default['sync_folder']:default['sync_folder']=drive_suggestion().get('sync_folder','')
        return default
    def save_config(self,values):
        config=self.config()
        for k in ('source','up','source_mode','route','local_folder','sync_folder','cadence','interval_hours','idle_minutes','idle_required','ac_only','auto_upload','cleanup_extras','modes','folder_id','folder_name'):
            if k in values:config[k]=values[k]
        if 'source' in values and 'source_mode' not in values:config['source_mode']='custom'
        if config['source_mode'] not in ('loader','custom') or config['route'] not in ('desktop','api'):raise ValueError('Invalid backup source or destination method.')
        if config['source_mode']=='loader':
            settings=self.archive.settings();config.update(source=settings.get('scan_start',''),up=settings.get('scan_up',0))
        if not config['local_folder']:config['local_folder']=str(self.data.resolve().parent/'Backups')
        config['up']=max(0,min(4,int(config['up'])))
        if config['cadence'] not in ('daily','weekly','custom') or config['modes'] not in ('both','full','progress'):raise ValueError('Invalid backup schedule.')
        if 'interval_hours' not in values and 'cadence' in values:config['interval_hours']=168 if values['cadence']=='weekly' else 24
        config['interval_hours']=max(1,min(168,int(config['interval_hours'])))
        config['cadence']='daily' if config['interval_hours']==24 else 'weekly' if config['interval_hours']==168 else 'custom'
        for key in ('idle_required','ac_only','auto_upload','cleanup_extras'):config[key]=bool(config[key])
        config['idle_minutes']=max(1,min(120,int(config['idle_minutes'])))
        if config['source'] and not Path(config['source']).expanduser().is_dir():raise ValueError('The export folder could not be found.')
        if config['folder_id'] and not re.fullmatch(r'[a-zA-Z0-9_-]+',config['folder_id']):raise ValueError('Invalid Google Drive folder ID.')
        for key in ('local_folder','sync_folder'):
            if config[key]:
                path=Path(config[key]).expanduser().resolve()
                if path.parent==path:raise ValueError('Choose a specific backup folder, not the root of a drive.')
                if path.exists() and not path.is_dir():raise ValueError('The backup destination must be a folder.')
                config[key]=str(path)
        write_json(self.config_path,config)
        if self.archive.profile:self.archive.profile.update(backup={k:v for k,v in config.items() if k!='task_name'})
        return config
    def scope(self):
        config=self.config();start,root=scan_boundary(config['source'],config['up']);return config,start,root
    def inventory(self,hashes=False,state=None):
        config,start,root=self.scope();excluded=tuple(Path(p).resolve() for p in (str(self.data),config['local_folder'],config['sync_folder']) if p)
        docs=discover_documents(start,root,self.cancel,self.app,excluded)
        links={}
        if hashes:files,fingerprint,missing=plan_files(root,(state or {}).get('hash_cache'),self.update,self.check,docs,excluded,links,state.setdefault('reference_cache',{}) if state is not None else None)
        else:
            paths=set(docs)|asset_paths(root,docs,self.check,excluded);files={p.relative_to(root).as_posix():{'size':p.stat().st_size} for p in paths};fingerprint='';missing=[]
        return config,root,files,fingerprint,missing,links
    def preview(self):
        # Preview checks file names and sizes, not multi-gigabyte contents or hashes.
        if self.status()['running']:raise ValueError('Wait for the current backup before checking its contents.')
        self.cancel.clear();config,root,files,*_=self.inventory();return dict(source=config['source'],up=config['up'],root=str(root),counts=counts(files),local_folder=config['local_folder'],route=config['route'])
    def local_path(self,mode):
        if mode not in ('full','progress'):raise ValueError('Unknown backup mode.')
        return Path(self.config()['local_folder'])/('Chat-Archive-'+mode.title()+'.zip')
    def open_local(self,path=None):return open_folder(path or self.config()['local_folder'],create=True)
    def ready(self,config):
        return bool(config['sync_folder'] and (Path(config['sync_folder']).is_dir() or Path(config['sync_folder']).parent.is_dir())) if config['route']=='desktop' else self.drive.status()['connected'] and bool(config['folder_id'])
    def publish_desktop(self,path,folder,slot,state):
        folder=Path(folder).expanduser().resolve()
        if not folder.is_dir():
            if not folder.parent.is_dir():raise ValueError('The Google Drive folder is unavailable. Make sure Drive for desktop is running and signed in.')
            folder.mkdir()
        target=folder/path.name;copy=slot.get('desktop_copy',{})
        if target.exists() and copy.get('path')==str(target) and copy.get('sha256')==slot['sha256'] and copy.get('size')==target.stat().st_size and copy.get('mtime_ns')==target.stat().st_mtime_ns:return
        if target.resolve()==path.resolve():raise ValueError('Choose separate local and Google Drive folders so local ZIP creation never uploads implicitly.')
        if shutil.disk_usage(folder).free<slot['size']+64*1024**2:raise ValueError('Not enough space in the synced folder. The completed local ZIP is kept.')
        temporary=folder/('.'+path.name+'.'+uuid.uuid4().hex+'.partial');done=0;sha=hashlib.sha256()
        try:
            with path.open('rb') as source,temporary.open('xb') as sink:
                while part:=source.read(1024*1024):
                    self.check();sink.write(part);sha.update(part);done+=len(part);self.update(phase='Copying to Google Drive folder',done=done,total=slot['size'],current=path.name)
            if sha.hexdigest()!=slot['sha256']:raise ValueError('The local ZIP changed during copying. Retry the backup.')
            self.check();os.replace(temporary,target)
        finally:
            if temporary.exists():temporary.unlink()
        stat=target.stat();slot['desktop_copy']=dict(path=str(target),sha256=slot['sha256'],size=stat.st_size,mtime_ns=stat.st_mtime_ns,copied_at=time.time());save_private(self.state_path,state)
    def state(self):return read_private(self.state_path)
    def status(self):
        try:progress=json.loads(self.status_path.read_text(encoding='utf-8')) if self.status_path.exists() else {}
        except (OSError,ValueError):progress={}
        running=False
        try:
            with job_lock(self.lock_path):pass
        except ValueError:running=True
        if not running and time.time()-progress.get('at',0)>5 and (progress.get('phase','').startswith(('Packaging','Uploading','Copying')) or progress.get('phase') in ('Preparing backup','Finding linked attachments','Checking backup changes','Unpacking archive','Integrating conversations')):
            progress={'phase':'Previous job stopped','message':'Run it again to continue. Completed backups and original files have been kept.'}
        state=self.state();public={k:state.get(k) for k in ('last_success','last_local','last_checked','last_fingerprint','missing_count','missing','last_import','source_counts','scope_root')}
        public['files']={k:{**{field:value.get(field) for field in ('id','webViewLink','sha256','size','uploaded_at','desktop_copy')},'path':str(self.local_path(k)),'exists':self.local_path(k).is_file()} for k,value in state.get('slots',{}).items()}
        return dict(config=self.config(),connection=self.drive.status(),progress=progress,running=running,**public)
    def update(self,**values):
        with self.progress_lock:
            if time.monotonic()-self.last_write<.25 and not values.get('force'):return
            values.pop('force',None);values.update(at=time.time());write_json(self.status_path,values);self.last_write=time.monotonic()
    def check(self):
        if self.cancel.is_set():raise InterruptedError('Cancelled. Completed backups and original exports are kept.')
        if self.scheduled:
            seconds=idle_seconds()
            if self.config()['idle_required'] and (seconds is None or seconds<self.config()['idle_minutes']*60):raise InterruptedError('Waiting for the computer to become idle again.')
        if self.scheduled and not power_allowed(self.config()):raise InterruptedError('Waiting for AC power.')
        # Give interactive work priority without letting a stalled read starve a backup.
        # Cancellation must also remain responsive during this short pause.
        if self.archive.foreground.is_set() and self.cancel.wait(.02):raise InterruptedError('Cancelled. Completed backups and original exports are kept.')
    def start(self,upload=True,scheduled=False):
        if self.worker and self.worker.is_alive():raise ValueError('A backup or import is already running.')
        self.cancel.clear();self.scheduled=scheduled;self.worker=threading.Thread(target=self._run,args=(upload,),daemon=True);self.worker.start();return {'started':True}
    def _run(self,upload):
        try:
            with job_lock(self.lock_path):self.run(upload)
        except InterruptedError as e:self.update(phase='Waiting' if self.scheduled else 'Cancelled',error=str(e),force=True)
        except Exception as e:self.update(phase='Needs attention',error=str(e),force=True)
    def run(self,upload=True):
        config=self.config();state=self.state();self.update(phase='Preparing backup',done=0,total=0,force=True)
        if not config['source']:raise ValueError('Choose the export folder first.')
        if upload and not self.ready(config):raise ValueError('Choose the Google Drive for desktop folder, or connect the optional direct account route. Local ZIP creation needs neither.')
        config,root,files,fingerprint,missing,links=self.inventory(True,state)
        self.folder=Path(config['local_folder']);self.folder.mkdir(parents=True,exist_ok=True)
        if not files:raise ValueError('No Markdown or JSON exports were found in this folder.')
        state['hash_cache']=files;state['last_checked']=time.time();state['missing_count']=len(missing);state['missing']=missing[:100];state['source_counts']=counts(files);state['scope_root']=str(root)
        settings=self.archive.settings();catalog=self.archive.catalog();organization=[{k:c.get(k) for k in ('id','category','pinned','position','alias','trashed','color','sticky')} for c in catalog];source_map=[];conversations=conversation_map(root,files,catalog)
        for c in conversations:
            related={p for doc in [*c.get('markdown',[]),*c.get('json',[])] for p in links.get(doc,[]) if p in files and p not in c.get('markdown',[]) and p not in c.get('json',[])};c['attachments']=sorted(set(c.get('attachments',[]))|related)
            for path in [*c.get('markdown',[]),*c.get('json',[])]:source_map.append(dict(path=path,**{k:c.get(k) for k in ('id','title','url','created','updated','kind','project')}))
        source_map.sort(key=lambda c:(c['path'],c['id']))
        safe_settings={k:v for k,v in settings.items() if k in ('categories','groupOrder','groupSort','sort','group','type','kindOverrides','theme','accent','bg','side','text','fontSize','width','showProjects','showDates','rememberPosition','positions','lastChat','pageSize','autoRefresh','rescanIntervalMinutes','collapsed','closedGroups')}
        presentation=dict(schema='offline-chat-viewer/v1',settings=safe_settings,organization=organization)
        setting_hash=hashlib.sha256(json.dumps(['linked-bundle-v2',presentation,source_map],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        fingerprint=hashlib.sha256((fingerprint+setting_hash).encode()).hexdigest()
        delivery=config['route']+':'+(config['sync_folder'] if config['route']=='desktop' else config['folder_id']);previous=state.get('baseline',{}) if upload and state.get('baseline_destination',delivery)==delivery else state.get('local_baseline',{}) if not upload else {};changed=progress_files(files,previous,conversations);deleted=sorted(set(previous)-set(files));slots=state.setdefault('slots',{})
        modes=['full','progress'] if config['modes']=='both' else [config['modes']]
        for mode in modes:
            self.check();selected=files if mode=='full' else changed;path=self.folder/('Chat-Archive-'+mode.title()+'.zip');slot=slots.setdefault(mode,{})
            manifest=dict(schema='offline-chat-viewer/backup-v1',mode=mode,fingerprint=fingerprint,base_fingerprint=state.get('last_fingerprint') if mode=='progress' else None,files=selected,conversations=[c for c in source_map if c['path'] in selected],deleted=deleted if mode=='progress' else [],missing=missing,source=dict(selected=config['source'],up=config['up'],root=str(root)),counts=counts(selected))
            if slot.get('fingerprint')!=fingerprint or slot.get('path')!=str(path) or not path.exists():
                required=sum(v['size'] for v in selected.values())
                if shutil.disk_usage(self.folder).free<required+128*1024**2:raise ValueError('Not enough free space to safely build the ZIP. Free space and retry; the previous backup is kept.')
                sha,md5=build_zip(root,path,selected,manifest,presentation,self.update,self.check,linked_index(selected,conversations,missing))
                if slot.get('sha256')!=sha:slot.pop('session',None)
                slot.update(sha256=sha,md5=md5,size=path.stat().st_size,fingerprint=fingerprint,path=str(path))
                save_private(self.state_path,state)
            if upload and config['route']=='desktop':self.publish_desktop(path,config['sync_folder'],slot,state)
            if upload and config['route']=='api' and (slot.get('uploaded_sha256')!=slot['sha256'] or slot.get('uploaded_folder')!=config['folder_id']):
                if slot.get('uploaded_folder') and slot['uploaded_folder']!=config['folder_id']:slot.pop('id',None);slot.pop('session',None)
                self.update(phase='Uploading '+mode+' backup',done=0,total=slot['size'],force=True)
                manager=self
                class IdleCancel:
                    def is_set(self):
                        idle=idle_seconds() if manager.scheduled else None
                        return manager.cancel.is_set() or manager.scheduled and (not power_allowed(config) or config['idle_required'] and (idle is None or idle<config['idle_minutes']*60))
                    def wait(self,seconds):
                        end=time.monotonic()+seconds
                        while time.monotonic()<end:
                            if self.is_set():return True
                            manager.cancel.wait(min(.5,end-time.monotonic()))
                        return self.is_set()
                result=self.drive.upload(path,config['folder_id'],slot,lambda:save_private(self.state_path,state),lambda done,total:self.update(phase='Uploading '+mode+' backup',done=done,total=total),IdleCancel())
                if result.get('md5Checksum')!=slot['md5'] or int(result.get('size',-1))!=slot['size']:raise ValueError('Google did not confirm matching backup bytes. Retry to verify the upload.')
                slot.update(result);slot.update(uploaded_sha256=slot['sha256'],uploaded_folder=config['folder_id'],uploaded_at=time.time());slot.pop('session',None);save_private(self.state_path,state)
        if upload:state.update(baseline=files,baseline_destination=delivery,last_fingerprint=fingerprint,last_success=time.time())
        else:state.update(local_baseline=files,last_local=time.time())
        if config['cleanup_extras']:state['cleanup']=self.cleanup(config,state,modes)
        save_private(self.state_path,state);self.update(phase='Copied to Google Drive folder' if upload and config['route']=='desktop' else 'Backups up to date' if upload else 'Local ZIPs ready',done=1,total=1,message='Google Drive for desktop handles uploading; check its sync status.' if upload and config['route']=='desktop' else 'Saved in '+str(self.folder),warning=(str(len(missing))+' file/path references could not be resolved locally. These can include example paths in saved code; discovered attachment files are included.' if missing else ''),force=True)
    def cleanup(self,config=None,state=None,modes=None):
        if config is None and self.status()['running']:raise ValueError('Wait for the current backup or import before cleaning up ZIPs.')
        config=config or self.config();state=state or self.state();modes=modes or (['full','progress'] if config['modes']=='both' else [config['modes']])
        owned=[v.get('path') for v in state.get('slots',{}).values()]
        moved=retire_extras(config['local_folder'],modes,owned)
        if config['route']=='desktop' and config['sync_folder']:moved+=retire_extras(config['sync_folder'],modes)
        return dict(retired=sum(not p.startswith('deduplicated:') for p in moved),deduplicated=sum(p.startswith('deduplicated:') for p in moved),paths=moved)
    def import_zip(self,path,restore_settings=False):
        if self.worker and self.worker.is_alive():raise ValueError('Wait for the current backup or import to finish.')
        path=Path(path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower()!='.zip':raise ValueError('Choose a saved ZIP archive.')
        self.cancel.clear();self.scheduled=False
        def run():
            try:
                with job_lock(self.lock_path):
                    root=self.data/'imports'/uuid.uuid4().hex;(self.data/'imports').mkdir(exist_ok=True);extract_zip(path,root,self.update,self.check)
                    mappings={}
                    if (root/'backup-manifest.json').exists():
                        metadata=json.loads((root/'backup-manifest.json').read_text(encoding='utf-8'))
                        if metadata.get('schema')=='offline-chat-viewer/backup-v1':
                            for c in metadata.get('conversations',[]):mappings.setdefault(c.get('path'),[]).append(c)
                    catalog={c['id']:c for c in self.archive.catalog()};indexed=skipped=0
                    discovered=discover_documents(root,root,self.cancel,self.app)
                    exporter_meta,by_path,manifests=metadata_sources(root,discovered)
                    for entry,manifest in manifests:
                        self.check();self.archive.register_manifest(entry,manifest,root)
                    documents=[p for p in discovered if p.name.lower() not in ('backup-manifest.json','viewer-settings.json','conversation-index.json','archive-index.json','export-report.json') and 'portable-state' not in p.name.lower()]
                    # JSON preserves branches, citations and attachments. Read each
                    # indexed conversation once when its Markdown twin also exists.
                    json_ids={by_path[str(p)][0]['id'] for p in documents if p.suffix.lower()=='.json' and str(p) in by_path}
                    documents=[p for p in documents if not (p.suffix.lower()=='.md' and str(p) in by_path and by_path[str(p)][0]['id'] in json_ids)]
                    documents.sort(key=lambda p:(p.suffix.lower()=='.md',str(p)))
                    for index,p in enumerate(documents):
                        self.check();self.update(phase='Integrating conversations',done=index+1,total=len(documents),current=p.name)
                        for item in self.archive.read_items(p):
                            source_meta=by_path.get(str(p),(exporter_meta.get(item['id'],{}),None))[0]
                            if source_meta:
                                item['id']=source_meta['id']
                                for key,target in (('create_time','created'),('update_time','updated')):
                                    if source_meta.get(key):item[target]=max(item.get(target) or 0,timestamp(source_meta[key])) if target=='updated' and p.suffix.lower()!='.md' else timestamp(source_meta[key])
                            relative=p.relative_to(root/'archive').as_posix() if p.is_relative_to(root/'archive') else ''
                            saved=mappings.get(relative,[])
                            meta=next((c for c in saved if c.get('id')==item['id']),saved[0] if p.suffix.lower()=='.md' and len(saved)==1 else None)
                            if meta:
                                item.update({k:meta[k] for k in ('id','title','url','created','updated','kind','project') if meta.get(k) is not None})
                            old=catalog.get(item['id']);new_count=len(item['messages'])
                            upgrade=old and Path(old.get('path','')).suffix.lower()=='.md' and p.suffix.lower()=='.json'
                            if old and (old.get('updated',0)>(item.get('updated') or 0) or old.get('updated',0)==(item.get('updated') or 0) and old.get('count',0)>=new_count and not upgrade):
                                if old.get('updated',0)==(item.get('updated') or 0):self.archive.enrich(item['id'],source_meta)
                                skipped+=1;continue
                            s=p.stat();self.archive.store(item,p,str(s.st_mtime_ns)+':'+str(s.st_size),root,source_meta);catalog[item['id']]=dict(item,count=new_count,path=str(p));indexed+=1
                    if restore_settings and (root/'viewer-settings.json').exists():
                        values=json.loads((root/'viewer-settings.json').read_text(encoding='utf-8'))
                        if values.get('schema')!='offline-chat-viewer/v1':raise ValueError('The archive contains an unrecognized settings backup.')
                        allowed=('categories','groupOrder','groupSort','sort','group','type','kindOverrides','theme','accent','bg','side','text','fontSize','width','showProjects','showDates','rememberPosition','positions','lastChat','pageSize','autoRefresh','rescanIntervalMinutes','collapsed','closedGroups')
                        self.archive.save_settings({k:v for k,v in values.get('settings',{}).items() if k in allowed});self.archive.organize_many(values.get('organization',[]))
                    if self.archive.ui_cache is not None:
                        catalog=self.archive.catalog()
                        with self.archive.ui_cache_lock:
                            self.archive.ui_cache['chats'].update({c['id']:c for c in catalog});self.archive.ui_cache['coverage']=self.archive.coverage();self.archive.ui_cache['revision']+=1;self.archive.ui_delta_floor=self.archive.ui_cache['revision']
                    state=self.state();state['last_import']=dict(at=time.time(),indexed=indexed,kept_newer=skipped);save_private(self.state_path,state);self.update(phase='Import complete',done=1,total=1,message=f'{indexed} new or newer conversations integrated; {skipped} existing newer copies kept.',force=True)
            except Exception as e:self.update(phase='Import needs attention',error=str(e),force=True)
        self.worker=threading.Thread(target=run,daemon=True);self.worker.start();return {'started':True}
    def due(self):
        config=self.config();seconds=idle_seconds();state=self.state()
        return config['enabled'] and (not config['auto_upload'] or self.ready(config)) and power_allowed(config) and (not config['idle_required'] or seconds is not None and seconds>=config['idle_minutes']*60) and time.time()-state.get('last_success' if config['auto_upload'] else 'last_local',0)>=interval_seconds(config)
    def start_scheduler(self):
        def loop():
            while not self.stop.wait(60):
                try:
                    if self.due() and not (self.worker and self.worker.is_alive()):self.start(upload=self.config()['auto_upload'],scheduled=True)
                except Exception:pass
        threading.Thread(target=loop,daemon=True).start()
    def schedule(self,enabled):
        config=self.config()
        if enabled and (not config['source'] or config['auto_upload'] and not self.ready(config)):raise ValueError('Choose the export folder and a Google Drive for desktop folder, or set up the optional direct account connection, before enabling scheduled backups.')
        if os.name!='nt':
            if enabled:raise ValueError('Backups while the viewer is closed currently require Windows. Manual backups remain available.')
            config['enabled']=False;write_json(self.config_path,config)
            if self.archive.profile:self.archive.profile.update(backup={k:v for k,v in config.items() if k!='task_name'})
            return config
        name='OfflineChatViewerBackup-'+hashlib.sha256(str(self.archive.profile.path if self.archive.profile else self.data.resolve()).encode()).hexdigest()[:12]
        if enabled:
            import xml.etree.ElementTree as ET
            ns='http://schemas.microsoft.com/windows/2004/02/mit/task';ET.register_namespace('',ns)
            task=ET.Element('{'+ns+'}Task',version='1.2')
            def add(parent,name,text=None,**attrs):
                e=ET.SubElement(parent,'{'+ns+'}'+name,attrs)
                if text is not None:e.text=str(text)
                return e
            triggers=add(task,'Triggers');trigger=add(triggers,'CalendarTrigger');repeat=add(trigger,'Repetition');add(repeat,'Interval','PT5M');add(repeat,'Duration','P1D');add(repeat,'StopAtDurationEnd','false');add(trigger,'StartBoundary',datetime.datetime.now().replace(hour=0,minute=0,second=0,microsecond=0).isoformat());add(trigger,'Enabled','true');daily=add(trigger,'ScheduleByDay');add(daily,'DaysInterval','1')
            principals=add(task,'Principals');principal=add(principals,'Principal',id='User');add(principal,'UserId',os.environ.get('USERDOMAIN','')+'\\'+os.environ.get('USERNAME',''));add(principal,'LogonType','InteractiveToken');add(principal,'RunLevel','LeastPrivilege')
            options=add(task,'Settings');add(options,'MultipleInstancesPolicy','IgnoreNew');add(options,'DisallowStartIfOnBatteries',str(config['ac_only']).lower());add(options,'StopIfGoingOnBatteries',str(config['ac_only']).lower());add(options,'StartWhenAvailable','true');idle=add(options,'IdleSettings');add(idle,'Duration',f"PT{config['idle_minutes']}M");add(idle,'WaitTimeout','PT23H');add(idle,'StopOnIdleEnd',str(config['idle_required']).lower());add(idle,'RestartOnIdle','true');add(options,'RunOnlyIfIdle',str(config['idle_required']).lower());add(options,'ExecutionTimeLimit','PT12H');add(options,'Enabled','true')
            actions=add(task,'Actions',Context='User');execute=add(actions,'Exec');python=self.app/'runtime/pythonw.exe'
            if not python.exists():python=self.app/'runtime/python.exe'
            add(execute,'Command',str(python));add(execute,'Arguments',subprocess.list2cmdline([str(self.app/'backup_job.py'),'--data-dir',str(self.data),'--scheduled']+(['--profile',str(self.archive.profile.path)] if self.archive.profile else [])));add(execute,'WorkingDirectory',str(self.app))
            xml=self.data/'backup-task.xml';ET.ElementTree(task).write(xml,encoding='utf-16',xml_declaration=True);command=['schtasks.exe','/Create','/TN',name,'/XML',str(xml),'/F']
        else:command=['schtasks.exe','/Delete','/TN',name,'/F']
        result=subprocess.run(command,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and enabled:raise ValueError('Windows could not register the idle backup task. Keep the viewer open for scheduled backups, or check Task Scheduler permissions.')
        config['enabled']=bool(enabled);config['task_name']=name;write_json(self.config_path,config)
        if self.archive.profile:self.archive.profile.update(backup={k:v for k,v in config.items() if k!='task_name'})
        return config
    def close(self):self.stop.set();self.cancel.set()
