import {contact as browserContact} from './viewer-transport.mjs';
// Optional English Autopilot 2.4.12 adapter. Runs inside its existing dashboard lock.
import {limited,succeeded,validId,conversationValid} from './core.mjs';
import {recordLimit,recordSuccess} from './awareness.mjs';
const schema='offline-viewer/delete-v1';
const enabled=c=>c?.enabled===true&&c.schema===schema&&Number.isFinite(c.updated)&&Date.now()/1000-c.updated<45&&c.updated<Date.now()/1000+10;
async function directory(root,name,create=false){return root.getDirectoryHandle(name,{create});}
export async function readQueue(root,path){if(!root)return null;try{let dir=root;const parts=path.split('/');for(const part of parts.slice(0,-1))dir=await directory(dir,part);const file=await (await dir.getFileHandle(parts.at(-1))).getFile();if(file.size>2*1024*1024)throw Error('Viewer queue file is too large');return JSON.parse(await file.text());}catch(e){if(e.name==='NotFoundError')return null;throw e;}}
export async function heartbeat({root,job,canEdit,connected,write,connection={}}){
 if(!root||!job||!canEdit)return;
 await write('.viewer-queue/bridge.json',JSON.stringify({schema,transport:true,version:'2.4.13+viewer-3',scope:job.scope.key,updated:Date.now()/1000,connected:!!connected,connection,capabilities:['delete-chat','verify-chat','shared-pacing'],note:'Library cleanup is local only; remote Library deletion is unsupported.'}));
}
async function checks(root,scope){
 try{const dir=await directory(await directory(root,'.viewer-queue'),'checks');let n=0;for await(const h of dir.values()){if(++n>1000)break;if(h.kind!=='file'||!h.name.endsWith('.json'))continue;const c=await readQueue(dir,h.name);if(c?.schema==='offline-viewer/status-v1'&&c.scope===scope&&validId(c.cid)&&/^[a-f0-9]{32}$/.test(c.id)&&Date.now()/1000-c.created<1800){const r=await readQueue(root,'.viewer-queue/check-receipts/'+c.id+'.json');if(!r||r.id!==c.id)return c;}}}catch(e){if(e.name!=='NotFoundError')throw e;}return null;
}
export async function pending(root,scope){
 if(!root)return false;const control=await readQueue(root,'.viewer-queue/control.json');
 if(enabled(control))try{const dir=await directory(await directory(root,'.viewer-queue'),'commands');let n=0;for await(const h of dir.values()){if(++n>2000)break;if(h.kind!=='file'||!h.name.endsWith('.json'))continue;const c=await readQueue(dir,h.name);if(c?.schema===schema&&c.scope===scope&&c.run===control.run){const receipt=await readQueue(root,'.viewer-queue/receipts/'+c.id+'.json');if(receipt?.run!==c.run||!['confirmed','failed','paused'].includes(receipt.state))return true;}}}catch(e){if(e.name!=='NotFoundError')throw e;}
 return !!await checks(root,scope);
}
async function statusTurn(engine,{root,bridge,write}){
 const c=await checks(root,engine.job.scope.key);if(!c)return false;
 let auth=false,errors=0;
 for(;;){
  await engine.holdPoint();if(await engine.paceRequest('read')===false)continue;
  const r=await bridge({op:'get',id:c.cid,path:'/backend-api/conversation/'+encodeURIComponent(c.cid),scope:engine.job.scope,lastLimitSeen:engine.job.lastLimitSeen||0});
  if(r.status===429){limited(engine.job.pace,r.retryAfter,engine.now());recordLimit(engine.job);await engine.save();continue;}
  if(r.status===401&&!auth){auth=true;await engine.io.refresh();continue;}
  if([401,403,409].includes(r.status)){const e=Error(r.error||'Reconnect to the same signed-in ChatGPT account');e.connection=true;e.name='Paused';throw e;}
  if(!r.ok&&![404,410].includes(r.status)){if(++errors<3){engine.job.pace.until=Math.max(engine.job.pace.until,engine.now()+15000*2**errors);await engine.save();continue;}await write('.viewer-queue/check-receipts/'+c.id+'.json',JSON.stringify({...c,state:'unknown',error:r.error||'Remote check failed',checked:Date.now()/1000}));return true;}
  if(r.ok){succeeded(engine.job.pace,engine.now());recordSuccess(engine.job,engine.now());await engine.save();}
  const valid=!r.ok||typeof r.data?.is_visible==='boolean'||conversationValid(r.data,c.cid);
  const state=!valid?'unknown':r.ok?(r.data?.is_visible===false?'deleted':'available'):'unavailable';
  await write('.viewer-queue/check-receipts/'+c.id+'.json',JSON.stringify({...c,state,verified:valid,checked:Date.now()/1000,detail:!valid?'ChatGPT returned an unrecognized conversation response.':state==='unavailable'?'Authenticated lookup could not access this chat; deletion is not proven.':''}));return true;
 }
}
export async function transportHeartbeat(engine,options){return browserContact(engine,{...options,readQueue},false);}
async function importBrowserReceipts(engine,{root,write,index}){
 let dir;try{dir=await directory(await directory(root,'.viewer-queue'),'receipts');}catch(e){if(e.name==='NotFoundError')return;throw e;}
 let count=0,changed=false;
 for await(const h of dir.values()){
  if(++count>2000)break;if(h.kind!=='file'||!h.name.endsWith('.json'))continue;
  const r=await readQueue(dir,h.name),job=engine.job,entry=job.entries[r?.cid];
  if(r?.schema!==schema||r.scope!==job.scope.key||r.verified!==true||r.state!=='confirmed'||r.remote_state!=='deleted'||!entry||job.viewerDeletes?.[r.cid]?.verified)continue;
  (job.viewerDeletes||={})[r.cid]={id:r.id,at:r.updated*1000,verified:true,contentHash:entry.contentHash,mode:r.mode};
  Object.assign(entry,{status:'viewer-deleted',remoteDeletedAt:r.updated*1000,refresh:false,attachmentPending:false,retryAt:0});changed=true;
  if(r.mode==='library')for(const file of Object.values(job.library?.entries||{})){
   if(file.conversationIds?.length===1&&file.conversationIds[0]===r.cid)Object.assign(file,{status:'viewer-deleted',viewerDeletedFor:r.cid,parked:true});
  }
 }
 if(changed){await engine.save();await index(engine.job);}
}
export async function turn(engine,{root,bridge,write,index}){
 await importBrowserReceipts(engine,{root,write,index});
 if(await browserContact(engine,{root,bridge,write,index,readQueue}))return true;
 const send=bridge;bridge=async args=>{try{return await send(args);}catch(error){error.connection=true;error.name='Paused';throw error;}};
 const control=await readQueue(root,'.viewer-queue/control.json');if(!enabled(control))return statusTurn(engine,{root,bridge,write});
 let dir;try{dir=await directory(await directory(root,'.viewer-queue'),'commands');}catch(e){if(e.name==='NotFoundError')return statusTurn(engine,{root,bridge,write});throw e;}
 let examined=0;
 for await(const handle of dir.values()){
  if(++examined>2000)throw Error('Viewer queue exceeds 2000 files; archive completed commands first.');
  if(handle.kind!=='file'||!handle.name.endsWith('.json'))continue;
  const c=await readQueue(dir,handle.name),job=engine.job;
  if(c?.executor==='browser-v1'||c?.schema!==schema||c.scope!==job.scope.key||c.run!==control.run||!validId(c.cid)||!/^[a-f0-9]{32}$/.test(c.id)||!['library','preserve'].includes(c.mode))continue;
  const old=await readQueue(root,'.viewer-queue/receipts/'+c.id+'.json');if(old?.run===c.run&&['confirmed','failed','paused'].includes(old.state))continue;
  const receipt=async(state,extra={})=>write('.viewer-queue/receipts/'+c.id+'.json',JSON.stringify({schema,id:c.id,cid:c.cid,scope:c.scope,run:c.run,state,updated:Date.now()/1000,...extra}));
  const active=async()=>{const next=await readQueue(root,'.viewer-queue/control.json');return enabled(next)&&next.run===c.run;};
  const entry=job.entries[c.cid];
  if(!entry){await receipt('failed',{error:'Conversation is absent from this exporter account. Reconnect and review.'});return true;}
  if(job.viewerDeletes?.[c.cid]?.verified){await receipt('confirmed',{verified:true,recovered:true});return true;}
  // Let the normal export lanes finish changed transcripts before a remote mutation.
  if(entry.status!=='saved'||entry.refresh)continue;
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
    const e=Error(r.error||'ChatGPT returned HTTP '+r.status);if([401,403,409].includes(r.status)){e.connection=true;e.name='Paused';}throw e;
   }
  };
  const previousGuard=engine.queueActive;engine.queueActive=active;
  try{
   // Verify first when recovering an uncertain request. The mutation itself is idempotent.
   let result=await request('get');if(!result){await receipt('paused');return true;}
   // A pre-existing 404 proves unavailability, not a successful deletion.
   if([404,410].includes(result.status)){
    (job.viewerAvailability||={})[c.cid]={state:'unavailable',at:Date.now()};
    await engine.save();await index(job);await receipt('confirmed',{verified:true,remote_state:'unavailable',message:'Unavailable on ChatGPT; local files retained'});return true;
   }
   if(typeof result.data?.is_visible!=='boolean'&&!conversationValid(result.data,c.cid))throw Error('Unrecognized conversation response; no deletion was sent.');
   let verified=result.data?.is_visible===false;
   if(!verified){const changed=await request('viewerDelete');if(!changed){await receipt('paused');return true;}result=await request('get');if(!result){await receipt('paused');return true;}verified=[404,410].includes(result.status)||result.data?.is_visible===false;}
   if(!verified)throw Error('ChatGPT did not confirm deletion. No local Library copies were removed.');
   (job.viewerDeletes||={})[c.cid]={id:c.id,at:Date.now(),verified:true,contentHash:entry.contentHash,mode:c.mode};
   Object.assign(entry,{status:'viewer-deleted',remoteDeletedAt:Date.now(),refresh:false,attachmentPending:false,retryAt:0});
   if(c.mode==='library')for(const file of Object.values(job.library?.entries||{})){
    if(file.conversationIds?.length===1&&file.conversationIds[0]===c.cid)Object.assign(file,{status:'viewer-deleted',viewerDeletedFor:c.cid,parked:true});
   }
   // Preserve the content hash and cache; receipt/tombstone is separate mutation state.
   await engine.save();await index(job);await receipt('confirmed',{verified:true,remote_state:'deleted',content_hash:entry.contentHash});
  }catch(e){if(e.connection){await receipt('retrying',{error:e.message});throw e;}if(e.name==='ViewerQueuePaused'){await receipt('paused');return true;}if(e.name==='Paused'){await receipt('paused',{error:e.message});throw e;}await receipt('failed',{error:e.message});}
  finally{engine.queueActive=previousGuard;}
  return true;
 }
 return statusTurn(engine,{root,bridge,write});
}
