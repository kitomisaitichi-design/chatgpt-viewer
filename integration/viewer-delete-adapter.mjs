// Optional English Autopilot 2.4.12 adapter. Runs inside its existing dashboard lock.
import {limited,succeeded,validId} from './core.mjs';
import {recordLimit,recordSuccess} from './awareness.mjs';
const schema='offline-viewer/delete-v1';
const enabled=c=>c?.enabled===true&&c.schema===schema&&Number.isFinite(c.updated)&&Date.now()/1000-c.updated<45&&c.updated<Date.now()/1000+10;
async function directory(root,name,create=false){return root.getDirectoryHandle(name,{create});}
async function read(root,path){try{let dir=root;const parts=path.split('/');for(const part of parts.slice(0,-1))dir=await directory(dir,part);const file=await (await dir.getFileHandle(parts.at(-1))).getFile();if(file.size>2*1024*1024)throw Error('Viewer queue file is too large');return JSON.parse(await file.text());}catch(e){if(e.name==='NotFoundError')return null;throw e;}}
export async function heartbeat({root,job,canEdit,connected,write}){
 if(!root||!job||!canEdit)return;
 await write('.viewer-queue/bridge.json',JSON.stringify({schema,version:'2.4.12+viewer-1',scope:job.scope.key,updated:Date.now()/1000,connected:!!connected,capabilities:['delete-chat','verify-chat','shared-pacing'],note:'Library cleanup is local only; remote Library deletion is unsupported.'}));
}
export async function pending(root,scope){
 if(!root)return false;const control=await read(root,'.viewer-queue/control.json');if(!enabled(control))return false;
 try{const dir=await directory(await directory(root,'.viewer-queue'),'commands');for await(const h of dir.values()){if(h.kind!=='file'||!h.name.endsWith('.json'))continue;const c=await read(dir,h.name);if(c?.schema===schema&&c.scope===scope&&c.run===control.run){const receipt=await read(root,'.viewer-queue/receipts/'+c.id+'.json');if(receipt?.run!==c.run||!['confirmed','failed','paused'].includes(receipt.state))return true;}}}catch(e){if(e.name!=='NotFoundError')throw e;}return false;
}
export async function turn(engine,{root,bridge,write,index}){
 const control=await read(root,'.viewer-queue/control.json');if(!enabled(control))return false;
 let dir;try{dir=await directory(await directory(root,'.viewer-queue'),'commands');}catch(e){if(e.name==='NotFoundError')return false;throw e;}
 let examined=0;
 for await(const handle of dir.values()){
  if(++examined>2000)throw Error('Viewer queue exceeds 2000 files; archive completed commands first.');
  if(handle.kind!=='file'||!handle.name.endsWith('.json'))continue;
  const c=await read(dir,handle.name),job=engine.job;
  if(c?.schema!==schema||c.scope!==job.scope.key||c.run!==control.run||!validId(c.cid)||!/^[a-f0-9]{32}$/.test(c.id)||!['library','preserve'].includes(c.mode))continue;
  const old=await read(root,'.viewer-queue/receipts/'+c.id+'.json');if(old?.run===c.run&&['confirmed','failed','paused'].includes(old.state))continue;
  const receipt=async(state,extra={})=>write('.viewer-queue/receipts/'+c.id+'.json',JSON.stringify({schema,id:c.id,cid:c.cid,scope:c.scope,run:c.run,state,updated:Date.now()/1000,...extra}));
  const active=async()=>{const next=await read(root,'.viewer-queue/control.json');return enabled(next)&&next.run===c.run;};
  const entry=job.entries[c.cid];
  if(!entry){await receipt('failed',{error:'Conversation is absent from this exporter account. Reconnect and review.'});return true;}
  if(job.viewerDeletes?.[c.cid]?.verified){await receipt('confirmed',{verified:true,recovered:true});return true;}
  // Let the normal export lanes finish changed transcripts before a remote mutation.
  if(entry.status!=='saved'||entry.refresh)return false;
  if(c.content_hash&&c.content_hash!==entry.contentHash){await receipt('failed',{error:'The exporter saved a newer revision. Review and run the queue again.'});return true;}
  await receipt('running',{message:'Waiting for the shared exporter scheduler'});
  const request=async(op)=>{
   let auth=false,errors=0;
   for(;;){
    await engine.holdPoint();if(!await active())return null;
    if(await engine.paceRequest('read')===false)continue;
    if(!await active())return null;
    if(op==='viewerDelete'&&(entry.refresh||entry.status!=='saved'||c.content_hash&&entry.contentHash!==c.content_hash))throw Error('Conversation changed while waiting. Review its new backup before deleting.');
    const r=await bridge({op,id:c.cid,path:'/backend-api/conversation/'+encodeURIComponent(c.cid),scope:job.scope,lastLimitSeen:job.lastLimitSeen||0});
    if(r.ok){succeeded(job.pace,engine.now());recordSuccess(job,engine.now());await engine.save();return r;}
    if(r.status===429){job.lastLimitSeen=Math.max(job.lastLimitSeen||0,r.observedAt||0);limited(job.pace,r.retryAfter,engine.now());recordLimit(job);await engine.save();await receipt('retrying',{message:'Rate limited; waiting on exporter cooldown'});continue;}
    if(r.status===401&&!auth){auth=true;await engine.io.refresh();continue;}
    if(op==='get'&&[404,410].includes(r.status))return r;
    if((!r.status||r.status>=500)&&++errors<3){job.pace.until=Math.max(job.pace.until,engine.now()+15000*2**errors);await engine.save();continue;}
    throw Error(r.error||'ChatGPT returned HTTP '+r.status);
   }
  };
  try{
   // Verify first when recovering an uncertain request. The mutation itself is idempotent.
   let result=await request('get');if(!result){await receipt('paused');return true;}
   let verified=[404,410].includes(result.status)||result.data?.is_visible===false;
   if(!verified){const changed=await request('viewerDelete');if(!changed){await receipt('paused');return true;}result=await request('get');if(!result){await receipt('paused');return true;}verified=[404,410].includes(result.status)||result.data?.is_visible===false;}
   if(!verified)throw Error('ChatGPT did not confirm deletion. No local Library copies were removed.');
   (job.viewerDeletes||={})[c.cid]={id:c.id,at:Date.now(),verified:true,contentHash:entry.contentHash,mode:c.mode};
   Object.assign(entry,{status:'viewer-deleted',remoteDeletedAt:Date.now(),refresh:false,attachmentPending:false,retryAt:0});
   if(c.mode==='library')for(const file of Object.values(job.library?.entries||{})){
    if(file.conversationIds?.length===1&&file.conversationIds[0]===c.cid)Object.assign(file,{status:'viewer-deleted',viewerDeletedFor:c.cid,parked:true});
   }
   // Preserve the content hash and cache; receipt/tombstone is separate mutation state.
   await engine.save();await index(job);await receipt('confirmed',{verified:true,content_hash:entry.contentHash});
  }catch(e){if(e.name==='Paused'){await receipt('paused',{error:e.message});throw e;}await receipt('failed',{error:e.message});}
  return true;
 }
 return false;
}
