"""Read exporter file catalogs, with bounded paths and streaming file delivery."""
import hashlib,json,mimetypes,os,shutil,tempfile,threading,time
from pathlib import Path,PurePosixPath
from exporter_bridge import entries as exporter_entries,read_metadata,META_LIMIT

IMAGE_EXT={'.png','.jpg','.jpeg','.gif','.webp','.avif','.bmp'}

def safe_relative(value):
    if not isinstance(value,str) or '\\' in value or ':' in value or '\x00' in value:return None
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in {'attachments','files','images','downloads','assets'}:return None
    return path.as_posix()

def read_index(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>META_LIMIT:return None
    try:return read_metadata(path)
    except (ValueError,OSError):return None

class FileCatalog:
    def __init__(self,archive):
        self.archive=archive;self.lock=threading.RLock();self.signature=None;self.entries={};self.notes=[]
    def manifests(self):
        with self.archive.connect() as db:paths=[Path(r['manifest']) for r in db.execute('SELECT DISTINCT manifest FROM manifest_entries')]
        with self.archive.connect() as db:paths.extend(Path(r['path']) for r in db.execute('SELECT path FROM exporter_manifests'))
        roots={p.parent.resolve() for p in paths}
        start=self.archive.settings().get('scan_start')
        if start:
            p=Path(start).expanduser().resolve()
            if p.is_file():p=p.parent
            if p.is_dir():
                roots.add(p)
                # The selected directory may be json/ inside an exporter backup.
                if p.name.lower() in ('json','markdown') and any((p.parent/name).is_file() for name in ('conversation-index.json','viewer-handoff.json','portable-state.json')):roots.add(p.parent)
        imports=self.archive.data_dir/'imports'
        if imports.is_dir():
            for p in imports.glob('*/conversation-index.json'):roots.add(p.parent.resolve())
            for p in imports.glob('*/attachments/library-index.json'):roots.add(p.parent.parent.resolve())
        out=[]
        for root in roots:
            for relative in ('portable-state.json','viewer-handoff.json','conversation-index.json','attachments/library-index.json'):
                path=root/relative
                if path.is_file():out.append((root,path))
        return sorted(out,key=lambda x:(x[1].name=='library-index.json',str(x[1])))
    def refresh(self):
        manifests=self.manifests();signature=[]
        for root,path in manifests:
            try:st=path.stat();signature.append((str(path),st.st_mtime_ns,st.st_size))
            except OSError:pass
        if signature==self.signature:return
        entries={};notes=[]
        for root,path in manifests:
            data=read_index(path)
            if not isinstance(data,dict):notes.append('Cannot read file catalog: '+path.name);continue
            library=path.name=='library-index.json'
            if library and data.get('schema')!='chatgpt-library-index/v1':notes.append('Unknown Library index format: '+str(path));continue
            rows=data.get('entries',[]) if library else exporter_entries(data)
            if not isinstance(rows,list):continue
            items=[(f,f.get('conversation_ids',[]),True) for f in data.get('library',[]) if isinstance(f,dict)] if isinstance(data.get('library'),list) else []
            for row in rows:
                if not isinstance(row,dict):continue
                if library:items.append((row,row.get('conversation_ids',[]),True))
                else:
                    for f in row.get('attachments',[]) if isinstance(row.get('attachments'),list) else []:
                        if isinstance(f,dict):items.append((f,[row.get('id')],False))
            for f,cids,file_library in items:
                fid=str((f.get('id') if f.get('historical') else f.get('file_id')) or f.get('id') or f.get('path') or f.get('name') or '')
                if not fid:continue
                key=hashlib.sha256((str(root)+'\0'+fid).encode()).hexdigest()[:32]
                relative=safe_relative(f.get('path')) or safe_relative(f.get('expected_path'))
                # safe_relative already rejects absolute paths and traversal. Resolve
                # only the selected file at delivery, not every missing Library path.
                target=root/relative if relative else None
                previous=entries.get(key,{})
                compatible_hash=not f.get('sha256') or f.get('sha256')==previous.get('sha256')
                if previous.get('target') and previous['target'].is_file() and compatible_hash and (not target or not target.is_file()) and (f.get('size') is None or previous.get('size')==f.get('size')):
                    target=previous['target'];relative=previous['relative']
                refs=[*previous.get('source_refs',[]),*(f.get('source_refs',[]) if isinstance(f.get('source_refs'),list) else [])]
                refs=[dict((k,str(r[k])) for k in ('kind','name','conversationId','presence','sourceKey') if r.get(k) is not None) for r in refs if isinstance(r,dict)]
                refs=list({tuple(sorted(r.items())):r for r in refs}.values())
                conversations=sorted({str(c) for c in [*previous.get('conversations',[]),*(cids if isinstance(cids,list) else []),*(r.get('conversationId') for r in refs)] if c})
                manual=f.get('manual_url') or 'https://chatgpt.com/library'
                if not str(manual).startswith('https://chatgpt.com/'):manual='https://chatgpt.com/library'
                sources=set(previous.get('sources',[]));sources.update(r['kind'] for r in refs if r.get('kind') in ('chat','library'))
                if file_library and not refs:sources.add('library')
                elif not file_library:sources.add('chat')
                retained=bool(f.get('historical')) or any(r.get('presence') not in (None,'','present') for r in refs)
                entries[key]={**previous,'key':key,'id':fid,'name':str(f.get('name') or f.get('filename') or fid),'size':f.get('size'),'mime':f.get('mime') or f.get('mime_type'),'status':f.get('status','unknown'),'error':str(f.get('error') or ''),'relative':relative,'root':root,'target':target,'conversations':conversations,'sha256':f.get('sha256') or (previous.get('sha256') if target==previous.get('target') else None),'manual_url':manual,'source':'library' if file_library else previous.get('source','attachment'),'source_refs':refs,'sources':sorted(sources),'historical':bool(f.get('historical')),'retained':retained,'duplicate_of':f.get('duplicate_of'),'version_info':f.get('version_info') if isinstance(f.get('version_info'),dict) else None}
        self.entries=entries;self.notes=notes;self.signature=signature
    def available_path(self,item):
        target=item['target']
        if not target:return None
        try:
            if target.is_symlink() or not target.resolve().is_relative_to(item['root']):return None
            st=target.stat()
            return target if target.is_file() and (item['size'] is None or st.st_size==item['size']) else None
        except OSError:return None
    def public(self,item):
        target=item['target'];exists=bool(target and target.is_file() and not target.is_symlink() and target.resolve().is_relative_to(item['root']));actual=target.stat().st_size if exists else None
        expected=item['size'];matches=exists and (expected is None or actual==expected)
        status='saved' if matches else 'missing' if item['status']=='saved' else item['status']
        return {k:item[k] for k in ('key','id','name','mime','error','conversations','manual_url','source','sha256','source_refs','sources','historical','retained','duplicate_of','version_info')} | {'size':actual if exists else expected,'status':status,'available':matches,'path':item['relative'],'image':bool(target and target.suffix.lower() in IMAGE_EXT)}
    def list(self,search='',status='all',conversation='',offset=0,limit=50,source='all'):
        with self.lock:
            self.refresh();rows=[self.public(e) for e in self.entries.values()]
            q=str(search).casefold();filtered=[r for r in rows if (not q or q in (' '.join([r['name'],r['id'],*(ref.get('name','') for ref in r['source_refs']),*r['conversations']])).casefold()) and (source=='all' or source in r['sources'] or source=='retained' and r['retained'] or source=='history' and r['historical']) and (not conversation or conversation in r['conversations']) and (status=='all' or status=='saved' and r['available'] or status=='manual' and not r['available'] and (r['status']=='manual' or isinstance(r['size'],(int,float)) and r['size']>=10_000_000) or status=='attention' and not r['available'])]
            filtered.sort(key=lambda r:(r['name'].casefold(),r['key']));offset=max(0,int(offset));limit=max(1,min(100,int(limit)))
            return {'entries':filtered[offset:offset+limit],'total':len(filtered),'offset':offset,'has_more':offset+limit<len(filtered),'counts':{'total':len(rows),'saved':sum(r['available'] for r in rows),'manual':sum(not r['available'] and (r['status']=='manual' or isinstance(r['size'],(int,float)) and r['size']>=10_000_000) for r in rows)},'notes':self.notes}
    def file(self,key):
        with self.lock:
            self.refresh();entry=self.entries.get(key)
            if not entry:raise FileNotFoundError('Unknown saved file.')
            target=self.available_path(entry)
            if not target:raise FileNotFoundError('Save a complete file into its expected backup path, or import a downloaded copy.')
            return target,entry
    def import_copy(self,key,source):
        with self.lock:
            self.refresh();entry=self.entries.get(key)
            if not entry or not entry['target']:raise ValueError('This item has no safe expected backup path. Update the exporter and rescan its Library.')
            source=Path(source).expanduser().resolve();target=entry['target']
            if not source.is_file():raise ValueError('Choose an existing downloaded file.')
            if entry['size'] is not None and source.stat().st_size!=entry['size']:raise ValueError('Downloaded file size does not match the Library metadata.')
            if source.stat().st_size<8192:
                try:
                    data=json.loads(source.read_text(encoding='utf-8-sig'))
                    if isinstance(data,dict) and data.get('status')=='error' and (data.get('error_type') or data.get('error_code')):raise ValueError('That file contains a service error, not the requested document.')
                except (UnicodeError,json.JSONDecodeError):pass
            if source==target:return self.public(entry)
            if target.exists():raise ValueError('A saved copy already exists at this path; it was kept.')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.parent.resolve().is_relative_to(entry['root']):raise ValueError('The backup path leaves its root.')
            fd,name=tempfile.mkstemp(prefix='.viewer-import-',dir=target.parent);os.close(fd);temporary=Path(name)
            try:
                shutil.copyfile(source,temporary)
                if entry['sha256']:
                    h=hashlib.sha256()
                    with temporary.open('rb') as f:
                        while part:=f.read(128*1024):h.update(part)
                    digest=h.hexdigest()
                    if digest!=entry['sha256']:raise ValueError('Downloaded file checksum differs from the saved metadata.')
                os.replace(temporary,target)
            finally:
                if temporary.exists():temporary.unlink()
            return self.public(entry)


def pick_downloaded_file():
    if os.name=='nt':
        import subprocess
        script="Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.OpenFileDialog; $f.Title='Choose your downloaded file'; $f.Filter='All files (*.*)|*.*'; $f.InitialDirectory=[Environment]::GetFolderPath('UserProfile')+'\\Downloads'; if($f.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Output $f.FileName}"
        result=subprocess.run(['powershell.exe','-NoProfile','-STA','-Command',script],capture_output=True,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.strip().lstrip('\ufeff')
    import tkinter as tk
    from tkinter import filedialog
    root=tk.Tk();root.withdraw()
    try:return filedialog.askopenfilename(title='Choose your downloaded file')
    finally:root.destroy()
