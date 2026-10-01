"""Preserve exported documents, linked assets and a browsable file index."""
import html,json,os,re,urllib.parse
from collections import defaultdict
from pathlib import Path
from discovery import SKIP_LOWER,iter_documents

ASSET_DIRS={'attachments','files','images','downloads','assets'}
META={'conversation-index.json','portable-state.json','export-report.json'}
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
    result={'markdown':0,'json':0,'jsonl':0,'attachments':0,'indexes':0,'files':len(files),'bytes':sum(v['size'] for v in files.values())}
    for path in files:
        name=Path(path).name.lower();ext=Path(path).suffix.lower()
        if is_asset(path):result['attachments']+=1
        elif name in META or name.startswith('portable-state'):result['indexes']+=1
        elif ext=='.md':result['markdown']+=1
        elif ext=='.json':result['json']+=1
        elif ext=='.jsonl':result['jsonl']+=1
        else:result['attachments']+=1
    return result

def conversation_map(root,files,catalog):
    root=Path(root).resolve();by_path={};records={}
    def register(record,paths):
        cid=str(record.get('id') or '')
        if not cid:return
        records[cid]={**records.get(cid,{}),**{k:v for k,v in record.items() if k in ('id','title','url','created','updated','kind','project') and v is not None}}
        for path in paths:
            if not isinstance(path,str):continue
            candidate=(root/path).resolve()
            if candidate.is_relative_to(root):by_path.setdefault(candidate.relative_to(root).as_posix(),set()).add(cid)
    for path in files:
        if Path(path).name.lower()!='conversation-index.json':continue
        manifest=root/path
        if manifest.stat().st_size>32*1024**2:continue
        try:
            data=json.loads(manifest.read_text(encoding='utf-8-sig'))
            for entry in data.get('entries',[]):
                if not isinstance(entry,dict):continue
                project=entry.get('project');project=project.get('title') or project.get('name') or '' if isinstance(project,dict) else project
                record={'id':entry.get('id'),'title':entry.get('title'),'url':entry.get('url'),'created':entry.get('create_time'),'updated':entry.get('update_time'),'kind':entry.get('chat_kind'),'project':project}
                register(record,[str((manifest.parent/entry[key]).relative_to(root)) for key in ('markdown','json') if isinstance(entry.get(key),str) and not Path(entry[key]).is_absolute()])
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
    assets=defaultdict(list)
    for path in files:
        if is_asset(path):
            for part in Path(path).parts:
                match=re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$',part,re.I)
                if match:assets[match[1]].append(path);break
    for cid,record in records.items():record['attachments']=assets.get(cid,[])
    return sorted([r for r in records.values() if r.get('markdown') or r.get('json')],key=lambda r:(str(r.get('title','')).casefold(),r['id']))

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
            if Path(path).name.lower() in META or Path(path).name.lower().startswith('portable-state'):selected[path]=files[path]
    return selected

def linked_index(files,conversations,missing):
    records=[]
    for record in conversations:
        item={**record};item.update({key:[p for p in record.get(key,[]) if p in files] for key in ('markdown','json','attachments')})
        if item['markdown'] or item['json']:records.append(item)
    index={'schema':'offline-chat-viewer/linked-index-v1','counts':counts(files),'conversations':records,'files':[dict(path='archive/'+p,**v) for p,v in sorted(files.items())],'missing':missing}
    esc=html.escape
    def link(path,label=None):return '<a href="'+esc(urllib.parse.quote('archive/'+path,safe='/'),quote=True)+'">'+esc(label or path)+'</a>'
    rows=[]
    for record in records:
        links=' · '.join(link(p,'Markdown' if p.endswith('.md') else 'JSON / session') for p in [*record['markdown'],*record['json']]);attachments='<br>'.join(link(p,Path(p).name) for p in record['attachments'])
        rows.append('<tr><td>'+esc(str(record.get('title') or record['id']))+'</td><td>'+links+'</td><td>'+attachments+'</td></tr>')
    all_files=''.join('<li>'+link(p)+'</li>' for p in sorted(files));summary=counts(files)
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"><title>Saved conversation archive</title><style>body{max-width:1200px;margin:40px auto;padding:0 24px;font:16px/1.6 system-ui;background:#16181c;color:#eee}a{color:#9dc5ff}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #ffffff20;vertical-align:top;overflow-wrap:anywhere}th{color:#aaa}td:first-child{width:34%}h1{letter-spacing:-.03em}summary{cursor:pointer}li{overflow-wrap:anywhere}p{color:#bbb}</style><h1>Saved conversation archive</h1><p>Extract this entire ZIP before opening links. Markdown, JSON and attachments are the original saved files. Use the portable viewer to read them with chat formatting.</p>'''
    page+='<p>'+str(summary['markdown'])+' Markdown files · '+str(summary['json'])+' JSON files · '+str(summary['attachments'])+' attachments · '+str(len(records))+' indexed conversations</p><table><thead><tr><th>Conversation</th><th>Saved text</th><th>Attachments</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><details><summary>All saved files and original indexes</summary><ul>'+all_files+'</ul></details>'
    if missing:page+='<p>'+str(len(missing))+' links are unavailable; see backup-manifest.json for details.</p>'
    return index,page+'</html>'
