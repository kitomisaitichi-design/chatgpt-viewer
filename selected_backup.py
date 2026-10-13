"""Selection-scoped backups: original message structure, local assets and receipts."""
import hashlib,json,os,shutil,time,urllib.parse,uuid
from pathlib import Path
from library_files import FileCatalog,IMAGE_EXT
from thread_images import ThreadImages
from thread_attachments import ThreadAttachments,thread_markdown
from export_bundle import FORMATS,counts,linked_index
from backup_snapshot import SnapshotPending

def selection(archive,ids,formats=None):
    if not isinstance(ids,list) or not ids or len(ids)>5000 or any(not isinstance(cid,str) for cid in ids):raise ValueError('Select between 1 and 5,000 conversations.')
    ids=list(dict.fromkeys(ids));formats=list(FORMATS) if formats is None else formats
    if not isinstance(formats,list) or any(f not in FORMATS for f in formats) or not {'markdown','json'}&set(formats):raise ValueError('Keep Markdown or JSON/session data in the selected backup.')
    by_id={c['id']:c for c in archive.catalog()}
    if any(cid not in by_id for cid in ids):raise ValueError('A selected conversation is no longer available. Refresh and select again.')
    return [by_id[cid] for cid in ids],[f for f in FORMATS if f in formats]

def rewrite(value,references):
    if isinstance(value,str):
        if value in references:return references[value]
        for old,new in sorted(references.items(),key=lambda item:len(item[0]),reverse=True):
            # Rebase explicit Markdown links without replacing words or home metadata.
            value=value.replace('](<'+old+'>)',']('+new+')').replace(']('+old+')',']('+new+')')
        return value
    if isinstance(value,list):return [rewrite(item,references) for item in value]
    if isinstance(value,dict):return {key:rewrite(item,references) for key,item in value.items()}
    return value

def prepare(archive,ids,formats=None,check=lambda:None):
    chats,formats=selection(archive,ids,formats);files=FileCatalog(archive);images=ThreadImages(archive,files);documents=ThreadAttachments(archive,files)
    plans=[];missing=[];asset_bytes=0;source_bytes=0;shared_sources=0
    all_chats=archive.catalog()
    for chat in chats:
        check();cid=chat['id'];source=Path(chat['path']);stat=source.stat();source_bytes+=stat.st_size;references={};assets={}
        if any(c['id']!=cid and c['path']==chat['path'] for c in all_chats):shared_sources+=1
        for catalog,resolver in ((images,images.file),(documents,documents.original)):
            for item in catalog.catalog(cid)['images']:
                check()
                try:target=resolver(cid,item['id'])
                except (OSError,ValueError):
                    # Folders and online links are navigation, not owned backup files.
                    if item.get('target') and Path(item['target']).is_dir():continue
                    from conversation_folders import resolve_folder
                    folder_link=False
                    for reference in item['references']:
                        try:resolve_folder(archive,cid,'reference',reference);folder_link=True;break
                        except (OSError,ValueError):pass
                    if folder_link:continue
                    for reference in item['references']:missing.append(dict(id=cid,document=chat['title'],reference=reference,reason='Saved file unavailable'))
                    continue
                if not target.is_file():continue
                category='images' if target.suffix.lower() in IMAGE_EXT else 'files'
                if category not in formats:continue
                key=str(target.resolve());name='assets/'+hashlib.sha256(key.encode()).hexdigest()[:20]+target.suffix.lower()
                if key not in assets:assets[key]=dict(path=target,relative=name,stat=(target.stat().st_size,target.stat().st_mtime_ns));asset_bytes+=target.stat().st_size
                for reference in item['references']:references[reference]=name;references[urllib.parse.quote(reference,safe='/\\:')]=name
        raw=None;native=None;markdown=None
        if 'json' in formats:
            if source.suffix.lower()=='.jsonl':
                try:native=[json.loads(line) for line in source.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
                except ValueError as error:raise SnapshotPending('The selected Codex session is still being written. Its completed backup will retry.') from error
                if not native or native[0].get('payload',{}).get('id')!=cid:raise ValueError('Selected session metadata does not match its ID.')
            else:raw,_=archive.source_data(cid)
        if 'markdown' in formats:
            if source.suffix.lower()=='.md' and any(c['id']!=cid and c['path']==chat['path'] for c in all_chats):raise ValueError('This Markdown source is shared by several chats. Select JSON/session data to keep the backup scoped.')
            markdown,_=thread_markdown(archive,cid)
        if (source.stat().st_size,source.stat().st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise SnapshotPending('A selected source changed while preparing the backup. Retrying without replacing completed ZIPs.')
        plans.append(dict(chat=chat,source=source,source_stat=(stat.st_size,stat.st_mtime_ns),assets=assets,references=references,raw=raw,native=native,markdown=markdown))
    missing=list({(item['id'],item['reference']):item for item in missing}.values())
    return dict(plans=plans,formats=formats,missing=missing,ids=[c['id'] for c in chats],bytes=source_bytes+asset_bytes,shared_sources=shared_sources)

def preview(archive,ids,formats=None):
    plan=prepare(archive,ids,formats)
    return dict(ids=plan['ids'],chats=[dict(id=p['chat']['id'],title=p['chat'].get('alias') or p['chat']['title'],kind=p['chat']['kind']) for p in plan['plans']],formats=plan['formats'],bytes=plan['bytes'],attachments=sum(len(p['assets']) for p in plan['plans']),missing=plan['missing'][:100],missing_count=len(plan['missing']),shared_sources=plan['shared_sources'])

def create(manager,job):
    from archive_backup import build_zip,digest
    manager.update(phase='Preparing selected backup',done=0,total=0,force=True)
    plan=prepare(manager.archive,job['ids'],job['formats'],manager.check)
    identifier=uuid.uuid4().hex;tree=manager.data/'selected-captures'/identifier;tree.mkdir(parents=True)
    files={};records=[];source_map=[]
    for position,p in enumerate(plan['plans']):
        manager.check();chat=p['chat'];base='selected/'+hashlib.sha256(chat['id'].encode()).hexdigest()[:24];folder=tree/base;folder.mkdir(parents=True)
        record={k:chat.get(k) for k in ('id','title','url','created','updated','kind','project','workspace','is_subagent','parent_id','agent_nickname')};record.update(markdown=[],json=[],attachments=[])
        def save(name,data):
            destination=folder/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data);return base+'/'+name
        if p['native'] is not None:record['json'].append(save('conversation.jsonl',('\n'.join(json.dumps(rewrite(row,p['references']),ensure_ascii=False) for row in p['native'])+'\n').encode()))
        elif p['raw']:record['json'].append(save('conversation.json',json.dumps(rewrite(p['raw'],p['references']),ensure_ascii=False).encode()))
        if p['markdown'] is not None:record['markdown'].append(save('conversation.md',rewrite(p['markdown'],p['references']).encode()))
        if not record['markdown'] and not record['json']:raise ValueError('No transcript was available for '+str(chat['title']))
        for asset in p['assets'].values():
            manager.check();target=folder/asset['relative'];target.parent.mkdir(parents=True,exist_ok=True);before=asset['path'].stat();shutil.copyfile(asset['path'],target);after=asset['path'].stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or (before.st_size,before.st_mtime_ns)!=asset['stat']:raise SnapshotPending('A linked asset changed during capture. Retrying the selected backup.')
            record['attachments'].append(base+'/'+asset['relative'])
        for relative in record['markdown']+record['json']+record['attachments']:
            path=tree/relative;stat=path.stat();files[relative]=dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=digest(path,manager.check)[0])
        for relative in record['markdown']+record['json']:source_map.append(dict(path=relative,**{k:record[k] for k in record if k not in ('markdown','json','attachments')}))
        records.append(record);manager.update(phase='Capturing selected chats',done=position+1,total=len(plan['plans']),current=chat['title'])
    destination=Path(job['destination']);destination.mkdir(parents=True,exist_ok=True)
    required=sum(v['size'] for v in files.values())
    if shutil.disk_usage(destination).free<required+128*1024**2:raise ValueError('Not enough space for the selected ZIP. Existing backups are kept.')
    path=destination/('Selected-Chats-'+time.strftime('%Y%m%d-%H%M%S')+'-'+identifier[:8]+'.zip')
    manifest=dict(schema='offline-chat-viewer/backup-v1',mode='selected',selection=plan['ids'],include_formats=plan['formats'],files=files,conversations=source_map,deleted=[],missing=plan['missing'],counts=counts(files))
    settings=manager.archive.settings();safe={k:settings[k] for k in ('theme','accent','fontSize','width','showDates','pageSize','sidebarLayout','hideSubagents') if k in settings}
    for key in ('positions','readChats','kindOverrides'):safe[key]={cid:value for cid,value in settings.get(key,{}).items() if cid in plan['ids']}
    presentation=dict(schema='offline-chat-viewer/v1',settings=safe,organization=[{k:c.get(k) for k in ('id','category','pinned','position','alias','trashed','color','sticky','bookmarked','kind_override')} for c in (p['chat'] for p in plan['plans'])])
    sha,_=build_zip(tree,path,files,manifest,presentation,manager.update,manager.check,linked_index(files,records,plan['missing']))
    receipt=dict(id=identifier,path=str(path),sha256=sha,size=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns,chats=len(plan['ids']),ids=plan['ids'],missing_count=len(plan['missing']),at=time.time(),formats=plan['formats'])
    from drive_backup import save_private
    state=manager.state();state['selected_exports']=[*state.get('selected_exports',[])[-9:],receipt];save_private(manager.state_path,state)
    manager.update(phase='Selected ZIP ready',done=1,total=1,message=str(len(plan['ids']))+' chats saved; '+str(len(plan['missing']))+' unavailable links recorded in the manifest.',force=True)
    # Captures are intermediate; the completed ZIP contains the verified copies.
    if not tree.resolve().is_relative_to((manager.data/'selected-captures').resolve()):raise ValueError('Capture cleanup path escaped the selected backup workspace.')
    shutil.rmtree(tree)
    return receipt
