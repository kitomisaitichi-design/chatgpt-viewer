"""Preserve exported documents, linked assets and a browsable file index."""
import csv,html,io,json,os,re,urllib.parse
from collections import defaultdict
from pathlib import Path
from discovery import SKIP_LOWER,iter_documents
from exporter_bridge import entries as exporter_entries,read_metadata

ASSET_DIRS={'attachments','files','images','downloads','assets'}
META={'conversation-index.json','portable-state.json','export-report.json','viewer-handoff.json'}
FORMATS=('markdown','json','images','files')
IMAGE_EXTS={'.png','.jpg','.jpeg','.gif','.webp','.svg','.avif','.bmp','.tif','.tiff','.heic','.heif','.ico'}

def file_kind(path):
    p=Path(path);name=p.name.lower();ext=p.suffix.lower()
    if name in META or name.startswith('portable-state') or name in ('library-index.json','manual-downloads.html'):return 'metadata'
    if is_asset(path):return 'images' if ext in IMAGE_EXTS else 'files'
    if ext=='.md':return 'markdown'
    if ext in ('.json','.jsonl'):return 'json'
    return 'images' if ext in IMAGE_EXTS else 'files'

def select_files(files,formats):
    return {p:v for p,v in files.items() if file_kind(p)=='metadata' or file_kind(p) in formats}

def save_state(files,conversations,mode):
    owners=defaultdict(set)
    for chat in conversations:
        for key in ('markdown','json','attachments'):
            for path in chat.get(key,[]):owners[path].add(str(chat['id']))
    rows=[dict(path='archive/'+p,original_path=p,kind=file_kind(p),size=v['size'],sha256=v.get('sha256',''),mtime_ns=v.get('mtime_ns',0),state='saved',mode=mode,conversation_ids=sorted(owners[p])) for p,v in sorted(files.items())]
    output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(['path','kind','bytes','sha256','mtime_ns','state','mode','conversation_ids'])
    def cell(value):
        value=str(value)
        return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value
    for row in rows:writer.writerow([cell(row[k]) if k!='conversation_ids' else cell(';'.join(row[k])) for k in ('path','kind','size','sha256','mtime_ns','state','mode','conversation_ids')])
    return {'schema':'offline-chat-viewer/save-state-v1','mode':mode,'files':rows},output.getvalue()
def is_asset(relative):return any(part.lower() in ASSET_DIRS for part in Path(relative).parts[:-1])
def documents(start,root,event,app,exclude=()):
    status={'errors':[]};result=list(iter_documents(start,root,event,status,app,exclude))
    if status['errors']:raise ValueError('Backup discovery: '+'; '.join(status['errors'][:4]))
    return result

def asset_paths(root,docs,check=lambda:None,exclude=()):
    roots=set();root=Path(root).resolve();excluded=tuple(Path(p).resolve() for p in exclude)
    for document in docs:
        parent=document.parent
        while parent.is_relative_to(root):
            for name in ASSET_DIRS:
                folder=parent/name
                if folder.is_dir() and not folder.is_symlink() and not any(folder.resolve().is_relative_to(p) for p in excluded):roots.add(folder)
            if parent==root:break
            parent=parent.parent
    visited=set();paths=set()
    for folder in sorted(roots):
        def failed(error):raise ValueError('Cannot read an attachment folder: '+str(error))
        for base,dirs,files in os.walk(folder,followlinks=False,onerror=failed):
            check();base=Path(base);resolved=base.resolve()
            if resolved in visited or any(resolved.is_relative_to(p) for p in excluded):dirs.clear();continue
            visited.add(resolved)
            if len(visited)>25000:raise ValueError('Attachment directory limit reached. Choose a narrower folder.')
            dirs[:]=[d for d in dirs if not d.startswith('.') and d.lower() not in SKIP_LOWER and not (base/d).is_symlink()]
            if len(base.relative_to(root).parts)>=24 and dirs:raise ValueError('Attachment depth limit reached. Choose a narrower folder.')
            for name in files:
                path=base/name
                if not path.is_symlink() and not name.startswith('.') and not name.lower().endswith('.error-response.json'):paths.add(path)
    return paths

def counts(files):
    result={'markdown':0,'json':0,'jsonl':0,'images':0,'miscellaneous':0,'attachments':0,'indexes':0,'files':len(files),'bytes':sum(v['size'] for v in files.values())}
    for path in files:
        name=Path(path).name.lower();ext=Path(path).suffix.lower()
        kind=file_kind(path)
        if kind=='metadata':result['indexes']+=1
        elif kind in ('images','files'):
            result['attachments']+=1;result['images' if kind=='images' else 'miscellaneous']+=1
        elif ext=='.md':result['markdown']+=1
        elif ext=='.json':result['json']+=1
        elif ext=='.jsonl':result['jsonl']+=1
        else:result['attachments']+=1
    return result

def conversation_map(root,files,catalog):
    root=Path(root).resolve();by_path={};records={};assets=defaultdict(set)
    def attach(manifest,item,cids):
        if not isinstance(item,dict):return
        for key in ('path','expected_path'):
            value=item.get(key)
            if not isinstance(value,str) or Path(value).is_absolute() or '..' in Path(value.replace('\\','/')).parts:continue
            candidate=(manifest/value).resolve()
            if candidate.is_relative_to(root):
                relative=candidate.relative_to(root).as_posix()
                if relative in files:
                    for cid in cids:
                        if cid:
                            cid=str(cid);assets[cid].add(relative);records.setdefault(cid,dict(id=cid,title=cid))
                    break
    def register(record,paths):
        cid=str(record.get('id') or '')
        if not cid:return
        records[cid]={**records.get(cid,{}),**{k:v for k,v in record.items() if k in ('id','title','url','created','updated','kind','project') and v is not None}}
        for path in paths:
            if not isinstance(path,str):continue
            candidate=(root/path).resolve()
            if candidate.is_relative_to(root):by_path.setdefault(candidate.relative_to(root).as_posix(),set()).add(cid)
    for path in files:
        name=Path(path).name.lower()
        if name not in ('conversation-index.json','viewer-handoff.json','library-index.json') and 'portable-state' not in name:continue
        manifest=root/path
        try:
            data=read_metadata(manifest)
            if not isinstance(data,dict):continue
            library=data.get('entries',[]) if name=='library-index.json' else data.get('library',[])
            base=manifest.parent.parent if name=='library-index.json' else manifest.parent
            for item in library if isinstance(library,list) else []:
                if isinstance(item,dict):
                    cids=item.get('conversation_ids');refs=item.get('source_refs')
                    attach(base,item,[*(cids if isinstance(cids,list) else []),*(r.get('conversationId') for r in (refs if isinstance(refs,list) else []) if isinstance(r,dict))])
            for entry in [] if name=='library-index.json' else exporter_entries(data):
                if not isinstance(entry,dict):continue
                project=entry.get('project');project=project.get('title') or project.get('name') or '' if isinstance(project,dict) else project
                record={'id':entry.get('id'),'title':entry.get('title'),'url':entry.get('url'),'created':entry.get('create_time'),'updated':entry.get('update_time'),'kind':entry.get('chat_kind'),'project':project}
                register(record,[str((manifest.parent/entry[key]).relative_to(root)) for key in ('markdown','json') if isinstance(entry.get(key),str) and not Path(entry[key]).is_absolute()])
                for item in entry.get('attachments',[]) if isinstance(entry.get('attachments'),list) else []:attach(manifest.parent,item,[entry.get('id')])
        except (ValueError,OSError,AttributeError):continue
    for chat in catalog:
        path=Path(chat.get('path','')).resolve()
        if path.is_relative_to(root):register(chat,[path.relative_to(root).as_posix()])
    for path in files:
        p=Path(path)
        if is_asset(path) or p.suffix.lower() not in ('.md','.json','.jsonl') or p.name.lower() in META or p.name.lower().startswith('portable-state'):continue
        if path not in by_path:
            match=re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$',p.stem,re.I);cid=match[1] if match else path
            by_path[path]={cid};records.setdefault(cid,dict(id=cid,title=p.stem))
    for path,cids in by_path.items():
        if path not in files:continue
        for cid in cids:
            record=records[cid];record.setdefault('markdown',[]);record.setdefault('json',[])
            record['markdown' if Path(path).suffix.lower()=='.md' else 'json'].append(path)
    for path in files:
        if is_asset(path):
            for part in Path(path).parts:
                match=re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$',part,re.I)
                if match:assets[match[1]].add(path);break
    for cid,record in records.items():record['attachments']=sorted(assets.get(cid,[]))
    return sorted([r for r in records.values() if r.get('markdown') or r.get('json') or r.get('attachments')],key=lambda r:(str(r.get('title','')).casefold(),r['id']))

def progress_files(files,previous,conversations):
    selected={k:v for k,v in files.items() if previous.get(k,{}).get('sha256')!=v['sha256']}
    for record in conversations:
        paths=[*record.get('markdown',[]),*record.get('json',[]),*record.get('attachments',[])]
        if any(path in selected for path in paths):
            for path in paths:
                if path in files:selected[path]=files[path]
    # The original export index is kept beside its own relative paths.
    if selected:
        for path in files:
            if file_kind(path)=='metadata':selected[path]=files[path]
    return selected

def linked_index(files,conversations,missing):
    records=[]
    for record in conversations:
        item={**record};item.update({key:[p for p in record.get(key,[]) if p in files] for key in ('markdown','json','attachments')})
        if item['markdown'] or item['json'] or item['attachments']:records.append(item)
    groups={kind:['archive/'+p for p in sorted(files) if file_kind(p)==kind] for kind in (*FORMATS,'metadata')}
    index={'schema':'offline-chat-viewer/linked-index-v1','counts':counts(files),'conversations':records,'groups':groups,'files':[dict(path='archive/'+p,original_path=p,kind=file_kind(p),**v) for p,v in sorted(files.items())],'missing':missing}
    esc=html.escape
    def link(path,label=None):return '<a href="'+esc(urllib.parse.quote('archive/'+path,safe='/'),quote=True)+'">'+esc(label or path)+'</a>'
    rows=[]
    for record in records:
        links=' · '.join(link(p,'Markdown' if p.endswith('.md') else 'JSON / session') for p in [*record['markdown'],*record['json']]);attachments='<br>'.join(link(p,Path(p).name) for p in record['attachments'])
        rows.append('<tr><td>'+esc(str(record.get('title') or record['id']))+'</td><td>'+links+'</td><td>'+attachments+'</td></tr>')
    all_files=''.join('<details><summary>'+label+' · '+str(len(groups[kind]))+'</summary><p><a href="indexes/'+kind+'.json">'+label+' index</a></p><ul>'+''.join('<li>'+link(p)+' <small>'+esc(str(v.get('sha256','')))+' · '+str(v['size'])+' bytes</small></li>' for p,v in sorted(files.items()) if file_kind(p)==kind)+'</ul></details>' for kind,label in [('markdown','Markdown'),('json','JSON and sessions'),('images','Images'),('files','Other files'),('metadata','Exporter metadata')]);summary=counts(files)
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"><title>Saved conversation archive</title><style>body{max-width:1200px;margin:40px auto;padding:0 24px;font:16px/1.6 system-ui;background:#16181c;color:#eee}a{color:#9dc5ff}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #ffffff20;vertical-align:top;overflow-wrap:anywhere}th{color:#aaa}td:first-child{width:34%}h1{letter-spacing:-.03em}summary{cursor:pointer}li{overflow-wrap:anywhere}p{color:#bbb}</style><h1>Saved conversation archive</h1><p>Extract this entire ZIP before opening links. Markdown, JSON and attachments are the original saved files. Use the portable viewer to read them with chat formatting.</p>'''
    page+='<p>'+str(summary['markdown'])+' Markdown files · '+str(summary['json'])+' JSON files · '+str(summary['attachments'])+' attachments · '+str(len(records))+' indexed conversations</p><p><a href="archive-index.json">Cross-link index</a> · <a href="save-state.json">Save state JSON</a> · <a href="save-state.csv">Save state table</a> · <a href="backup-manifest.json">Backup manifest</a> · <a href="viewer-settings.json">Viewer preferences</a></p><table><thead><tr><th>Conversation</th><th>Saved text</th><th>Attachments</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'+all_files
    if missing:page+='<p>'+str(len(missing))+' links are unavailable; see backup-manifest.json for details.</p>'
    return index,page+'</html>'
