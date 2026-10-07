"""Read exporter metadata without coupling the viewer to one exporter version."""
import json,threading,time
import datetime
from collections import OrderedDict
from pathlib import Path

ALIASES={'createTime':'create_time','created':'create_time','updateTime':'update_time','updated':'update_time','chatKind':'chat_kind','chatKindEvidence':'kind_evidence','chat_kind_evidence':'kind_evidence','jsonPath':'json','markdownPath':'markdown','md':'markdown','conversation_id':'id'}

def normalize_entry(value,cid=''):
    if not isinstance(value,dict):return None
    entry=dict(value)
    for old,new in ALIASES.items():
        if old in entry and new not in entry:entry[new]=entry[old]
    entry['id']=str(entry.get('id') or cid)
    if not entry['id']:return None
    files=entry.get('files')
    if isinstance(files,dict):
        for key in ('json','markdown'):
            if not entry.get(key):entry[key]=files.get(key)
    basename=entry.get('basename')
    if isinstance(basename,str) and basename:
        entry.setdefault('json','json/'+basename+'.json');entry.setdefault('markdown','markdown/'+basename+'.md')
    project=entry.get('project')
    if isinstance(project,dict):entry['project']=project.get('title') or project.get('name') or ''
    return entry

def entries(data):
    """Merge portable job state first and its richer saved index last."""
    if not isinstance(data,dict):return []
    merged={}
    for block in (data.get('job'),data.get('index'),data):
        if not isinstance(block,dict):continue
        rows=block.get('entries') or block.get('conversations') or []
        pairs=rows.items() if isinstance(rows,dict) else (('',v) for v in rows) if isinstance(rows,list) else []
        for key,value in pairs:
            entry=normalize_entry(value,key)
            if entry:merged[entry['id']]={**merged.get(entry['id'],{}),**entry}
    return list(merged.values())

META_LIMIT=128*1024**2
_metadata_cache=OrderedDict();_metadata_lock=threading.RLock()

def read_metadata(path):
    """Share fingerprinted metadata only; do not retain exporter logs/job internals."""
    path=Path(path);stat=path.stat();key=(str(path.resolve()),stat.st_size,stat.st_mtime_ns)
    if stat.st_size>META_LIMIT:raise ValueError('Exporter metadata exceeds the 128 MiB limit.')
    with _metadata_lock:
        if key in _metadata_cache:_metadata_cache.move_to_end(key);return _metadata_cache[key]
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        after=path.stat()
        if (after.st_size,after.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise ValueError(path.name+' changed while reading. Retry after the exporter finishes saving.')
        if isinstance(data,dict):
            data={**{k:data[k] for k in ('schema','version','library') if k in data},'entries':data.get('entries',[]) if data.get('schema')=='chatgpt-library-index/v1' else entries(data)}
        for old in list(_metadata_cache):
            if old[0]==key[0]:del _metadata_cache[old]
        _metadata_cache[key]=data
        while len(_metadata_cache)>1 and (len(_metadata_cache)>4 or sum(k[1] for k in _metadata_cache)>META_LIMIT):_metadata_cache.popitem(last=False)
        return data

def read_index(path):return entries(read_metadata(path))

def timestamp(value):
    try:
        n=float(value or 0);return n/1000 if n>1e12 else n
    except (ValueError,TypeError):
        try:return datetime.datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
        except (ValueError,TypeError):return 0

def metadata_sources(root,documents):
    by_id={};by_path={};manifests=[]
    indexes=sorted((p for p in documents if p.name.lower() in ('viewer-handoff.json','conversation-index.json') or 'portable-state' in p.name.lower()),key=lambda p:(p.name.lower()=='conversation-index.json',p.name.lower()!='viewer-handoff.json',str(p)))
    for manifest in indexes:
        for entry in read_index(manifest):
            entry={**by_id.get(entry['id'],{}),**entry};by_id[entry['id']]=entry
            manifests.append((entry,manifest))
            for key in ('json','markdown'):
                path=saved_path(manifest.parent,entry.get(key))
                if path:by_path[str(path)]=(entry,manifest)
    return by_id,by_path,manifests

def saved_path(root,value):
    if not isinstance(value,str) or not value:return None
    root=Path(root).resolve();p=(root/value.replace('\\','/')).resolve()
    return p if p.is_relative_to(root) and p.is_file() else None

def attachment_records(entry,root):
    result=[];seen=set()
    attachments=entry.get('attachments') or []
    if not isinstance(attachments,list):return result
    for item in attachments[:5000]:
        if isinstance(item,str):item={'path':item}
        if not isinstance(item,dict):continue
        path=saved_path(root,item.get('path')) or saved_path(root,item.get('expected_path')) or saved_path(root,item.get('sourcePath'))
        key=str(path) if path else str(item.get('id') or item.get('name') or '')
        if key in seen:continue
        seen.add(key)
        actual=path.stat().st_size if path else None;expected=item.get('size');complete=bool(path) and (not isinstance(expected,(int,float)) or actual==expected)
        result.append(dict(id=str(item.get('id') or item.get('file_id') or ''),name=str(item.get('name') or (path.name if path else 'Saved file')),path=str(path) if path else '',relative=path.relative_to(Path(root).resolve()).as_posix() if path else '',available=complete,status='saved' if complete else 'incomplete' if path else str(item.get('status') or 'unavailable'),size=actual if path else expected or 0,mime=str(item.get('mime') or '')))
    return result

_cache=OrderedDict();_lock=threading.Lock();_roots_cache={}
def inspect_folder(path):
    selected=Path(path).expanduser().resolve()
    if not selected.is_dir():raise ValueError('Choose an existing exporter folder.')
    parent=selected.parent
    root=parent if selected.name.lower() in ('json','markdown','html','attachments','files') and (any((parent/n).is_file() for n in ('conversation-index.json','portable-state.json','conversations.json','viewer-handoff.json')) or (parent/'json').is_dir() and (parent/'markdown').is_dir()) else selected
    from discovery import iter_documents
    names=('viewer-handoff.json','portable-state.json','conversation-index.json')
    with _lock:cached_roots=_roots_cache.get(str(root))
    if cached_roots and time.monotonic()-cached_roots[0]<10:indexes=cached_roots[1]
    else:
        status={'errors':[]}
        indexes=[p for p in iter_documents(root,root,threading.Event(),status,Path(__file__).parent) if p.name in names]
        if status['errors']:raise ValueError('Export inspection: '+'; '.join(status['errors'][:4]))
        with _lock:
            _roots_cache[str(root)]=(time.monotonic(),indexes)
            if len(_roots_cache)>6:_roots_cache.pop(next(iter(_roots_cache)))
    indexes=[p for p in indexes if p.is_file()]
    indexes.sort(key=lambda p:(p.name=='conversation-index.json',p.name!='viewer-handoff.json',str(p)))
    fingerprint=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in indexes);key=(str(root),fingerprint)
    with _lock:
        cached=_cache.get(key)
        if cached and time.monotonic()-cached[0]<10:return dict(cached[1])
    merged={};owners={};warnings=[];version=''
    for p in indexes:
        try:
            data=read_metadata(p)
            if isinstance(data,dict):version=str(data.get('version') or version)
            for e in entries(data):merged[e['id']]={**merged.get(e['id'],{}),**e};owners[e['id']]=p.parent
        except (ValueError,OSError) as error:warnings.append(p.name+': '+str(error))
    available=missing=pending=0
    for e in merged.values():
        owner=owners[e['id']]
        if saved_path(owner,e.get('json')) or saved_path(owner,e.get('markdown')):available+=1
        else:missing+=1
        if e.get('attachment_pending') or e.get('attachmentPending'):pending+=1
    standard=(root/'conversations.json').is_file()
    result=dict(root=str(root),selected=str(selected),format='ChatGPT Exporter' if indexes else 'ChatGPT data export' if standard else 'Conversation folder',exporter_version=version,expected=len(merged),available=available,missing=missing,pending_attachments=pending,has_index=bool(indexes),has_library=(root/'attachments/library-index.json').is_file(),has_handoff=(root/'viewer-handoff.json').is_file(),has_json=(root/'json').is_dir() or standard,has_markdown=(root/'markdown').is_dir(),warnings=warnings,generated_at=time.time())
    roots=sorted({p.parent for p in indexes});result['exporter_roots']=[str(p) for p in roots]
    for flag,relative in (('has_library','attachments/library-index.json'),('has_handoff','viewer-handoff.json'),('has_json','json'),('has_markdown','markdown')):result[flag]|=any((p/relative).exists() for p in roots)
    with _lock:
        _cache[key]=(time.monotonic(),dict(result));_cache.move_to_end(key)
        while len(_cache)>6:_cache.popitem(last=False)
    return result
