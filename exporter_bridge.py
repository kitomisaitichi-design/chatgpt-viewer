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

def read_index(path):
    path=Path(path)
    if path.stat().st_size>32*1024**2:raise ValueError('Exporter metadata exceeds the 32 MB limit.')
    return entries(json.loads(path.read_text(encoding='utf-8-sig')))

def timestamp(value):
    try:
        n=float(value or 0);return n/1000 if n>1e12 else n
    except (ValueError,TypeError):
        try:return datetime.datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
        except (ValueError,TypeError):return 0

def metadata_sources(root,documents):
    by_id={};by_path={};manifests=[]
    indexes=sorted((p for p in documents if p.name.lower()=='conversation-index.json' or 'portable-state' in p.name.lower()),key=lambda p:(p.name.lower()=='conversation-index.json',str(p)))
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

_cache=OrderedDict();_lock=threading.Lock()
def inspect_folder(path):
    selected=Path(path).expanduser().resolve()
    if not selected.is_dir():raise ValueError('Choose an existing exporter folder.')
    parent=selected.parent
    root=parent if selected.name.lower() in ('json','markdown','html','attachments','files') and (any((parent/n).is_file() for n in ('conversation-index.json','portable-state.json','conversations.json')) or (parent/'json').is_dir() and (parent/'markdown').is_dir()) else selected
    indexes=[root/n for n in ('portable-state.json','conversation-index.json') if (root/n).is_file()]
    fingerprint=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in indexes);key=(str(root),fingerprint)
    with _lock:
        cached=_cache.get(key)
        if cached and time.monotonic()-cached[0]<10:return dict(cached[1])
    merged={};warnings=[]
    for p in indexes:
        try:
            for e in read_index(p):merged[e['id']]={**merged.get(e['id'],{}),**e}
        except (ValueError,OSError) as error:warnings.append(p.name+': '+str(error))
    available=missing=pending=0
    for e in merged.values():
        if saved_path(root,e.get('json')) or saved_path(root,e.get('markdown')):available+=1
        else:missing+=1
        if e.get('attachment_pending') or e.get('attachmentPending'):pending+=1
    standard=(root/'conversations.json').is_file()
    result=dict(root=str(root),selected=str(selected),format='ChatGPT Exporter' if indexes else 'ChatGPT data export' if standard else 'Conversation folder',expected=len(merged),available=available,missing=missing,pending_attachments=pending,has_index=bool(indexes),has_json=(root/'json').is_dir() or standard,has_markdown=(root/'markdown').is_dir(),warnings=warnings,generated_at=time.time())
    with _lock:
        _cache[key]=(time.monotonic(),dict(result));_cache.move_to_end(key)
        while len(_cache)>6:_cache.popitem(last=False)
    return result
