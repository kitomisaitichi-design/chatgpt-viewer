"""Install a narrowly versioned optional bridge; saves a complete rollback first."""
import json, shutil, sys, zipfile
from pathlib import Path

def install(folder):
    folder=Path(folder).expanduser().resolve()
    if json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['version']!='2.4.12':raise ValueError('This bridge supports exporter 2.4.12 only; keep newer exporter files intact.')
    names=('app.mjs','engine.mjs','bridge.js','core.mjs');source={name:(folder/name).read_text(encoding='utf-8') for name in names}
    if 'viewer-delete-adapter.mjs' in source['app.mjs']:return 'Already installed'
    changes={}
    app=source['app.mjs'];app="import * as viewerQueue from './viewer-delete-adapter.mjs';\n"+app
    target='maintenance:maintenanceTurn,libraryLimit:'
    if app.count(target)!=1:raise ValueError('Exporter engine setup differs; no files were changed')
    app=app.replace(target,"viewerQueue:e=>viewerQueue.turn(e,{root,bridge,write,index}),"+target)
    app=app.replace('content_hash:e.contentHash || null,previous_content_hash:', "content_hash:e.contentHash || null,remote_deleted_at:e.remoteDeletedAt || null,deletion_verified:!!j.viewerDeletes?.[e.id]?.verified,previous_content_hash:")
    app+='''\n// Local inbox polling never issues network work outside the existing Engine.
setInterval(async()=>{if(!canEdit||!root||!job)return;try{await viewerQueue.heartbeat({root,job,canEdit,connected,write});if(connected&&!running&&!starting&&!detecting&&await viewerQueue.pending(root,job.scope.key))await start(false,true);}catch(e){notice='Viewer queue: '+e.message;update();}},5000);
'''
    changes['app.mjs']=app
    engine=source['engine.mjs'];target='await this.holdPoint();await this.observe();\n        const pending='
    if engine.count(target)!=1:raise ValueError('Exporter scheduler differs; no files were changed')
    engine=engine.replace(target,'await this.holdPoint();await this.observe();\n        if(await this.io.viewerQueue?.(this))continue;\n        const pending=')
    # Discovery cannot resurrect a confirmed remote deletion, even after restart.
    engine=engine.replace("if(existing?.observedBodyHash===item.contentHash", "if(this.job.viewerDeletes?.[item.id]?.verified)continue;\n        if(existing?.observedBodyHash===item.contentHash")
    engine=engine.replace("if(!validId(item.id) || !item.revision", "if(this.job.viewerDeletes?.[item.id]?.verified)continue;\n        if(!validId(item.id) || !item.revision")
    engine=engine.replace('const before={...this.job.entries[item.id]},wasRefresh=', 'if(this.job.viewerDeletes?.[item.id]?.verified || this.job.entries[item.id]?.remoteDeletedAt)continue;\n      const before={...this.job.entries[item.id]},wasRefresh=')
    changes['engine.mjs']=engine
    core=source['core.mjs'];target='export function mergeEntry(job, item'
    pos=core.find(target)
    if pos<0:
        target='export function mergeEntry(job,item';pos=core.find(target)
    if pos<0:raise ValueError('Exporter merge contract differs; no files were changed')
    brace=core.index('{',pos);core=core[:brace+1]+"\n  if(job.viewerDeletes?.[item?.id]?.verified || job.entries?.[item?.id]?.remoteDeletedAt)return false;"+core[brace+1:]
    core=core.replace('if (!validId(id)) return false;', '''if (!validId(id)) return false;
  if(item.remote_deleted_at && item.deletion_verified){(job.viewerDeletes ||= {})[id]={at:item.remote_deleted_at,verified:true,contentHash:item.content_hash};job.entries[id]={...item,id,status:'viewer-deleted',remoteDeletedAt:item.remote_deleted_at,contentHash:item.content_hash};return true;}''',1)
    changes['core.mjs']=core
    bridge=source['bridge.js'];target="if (args.op !== 'get' || !allowed(args.path))"
    if bridge.count(target)!=1:raise ValueError('Exporter authentication bridge differs; no files were changed')
    addition='''if(args.op==='viewerDelete'){
        if(!/^[a-zA-Z0-9_-]{8,160}$/.test(args.id||''))return {ok:false,status:400,error:'Invalid conversation ID'};
        if(lastLimit&&lastLimit.at>(args.lastLimitSeen||0))return {ok:false,status:429,retryAfter:lastLimit.retryAfter,observedAt:lastLimit.at};
        const response=await originalFetch('/backend-api/conversation/'+encodeURIComponent(args.id),{method:'PATCH',credentials:'include',headers:{...authHeaders(args.scope),accept:'application/json','content-type':'application/json'},body:JSON.stringify({is_visible:false}),signal:AbortSignal.timeout(60000)});
        if(response.status===401){token=null;sessionAt=0;}
        if(!matches(args.scope))return {ok:false,status:409,error:'Workspace changed during deletion'};
        return {ok:response.ok,status:response.status,retryAfter:response.headers.get('retry-after')};
      }
      '''
    bridge=bridge.replace(target,addition+target);changes['bridge.js']=bridge
    backup=folder/'viewer-bridge-rollback.zip'
    if backup.exists():raise ValueError('A previous rollback exists; restore or inspect it before reinstalling')
    with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
        for name in names:z.write(folder/name,name)
    for name,value in changes.items():(folder/name).write_text(value,encoding='utf-8',newline='\n')
    shutil.copy2(Path(__file__).with_name('viewer-delete-adapter.mjs'),folder/'viewer-delete-adapter.mjs')
    return 'Installed. Reload the unpacked exporter extension and its ChatGPT tab; reconnect its existing backup folder.'

if __name__=='__main__':print(install(sys.argv[1]))
