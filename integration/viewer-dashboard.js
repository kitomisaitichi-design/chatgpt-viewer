// Viewer queue adapter v2: one owner, no full inventory scan before remote commands.
let viewerBusy=false,viewerAuthAt=0;
async function viewerTick(){
 if(viewerBusy||!canEdit||initializing||starting||detecting||!job?.scope||!folder)return;
 viewerBusy=true;
 try{
  if(await folder.queryPermission({mode:'readwrite'})!=='granted')return;
  root ||= folder;
  const reset=await viewerQueue.readQueue(root,'.viewer-queue/reconnect.json');
  let state=await db.get('meta',`viewerConnection:${job.scope.key}`)||{};
  const reconnect=state.nonce!==(reset?.nonce||'');
  if(reconnect){connected=false;viewerAuthAt=0;}
  if(!connected){
   if(running)return;
   if(!await viewerQueue.pending(root,job.scope.key)&&!reconnect)return;
   const expected=job.scope.key;
   connected=await viewerRunner.connectionState({db,root,scope:job.scope,connect:()=>connect(expected,true),write,sleep});
   root ||= folder;state=await db.get('meta',`viewerConnection:${expected}`)||{};
   if(!connected){await viewerQueue.heartbeat({root,job,canEdit,connected:false,write,connection:state});return;}
   viewerAuthAt=Date.now();
  }
  if(!running&&Date.now()-viewerAuthAt>30000){
   const context=await bridge({op:'context'});
   const key=context.ok?await digest(JSON.stringify([context.scope.user,context.scope.account||null])):null;
   if(!context.ok||key!==job.scope.key){connected=false;viewerAuthAt=0;await viewerQueue.heartbeat({root,job,canEdit,connected:false,write,connection:{error:context.error||'Sign in to the original account/workspace'}});return;}
   viewerAuthAt=Date.now();
  }
  await viewerQueue.heartbeat({root,job,canEdit,connected,write,connection:state});
  if(running||!await viewerQueue.pending(root,job.scope.key))return;
  running=true;update();
  try{
   const queueBridge=async args=>{try{return await bridge(args);}catch(error){error.connection=true;error.name='Paused';throw error;}};
   await viewerRunner.drain(Engine,job,{save:j=>db.put('jobs',scope.key,j),changed:update,sense,connection:()=>db.get('meta',`viewerConnection:${job.scope.key}`),online:()=>navigator.onLine,refresh:async()=>{const r=await queueBridge({op:'context'});const key=r.ok?await digest(JSON.stringify([r.scope.user,r.scope.account||null])):null;if(!r.ok||key!==job.scope.key){const e=Error(r.error||'Reconnect to the original ChatGPT account');e.connection=true;e.name='Paused';throw e;}}},{root,bridge:queueBridge,write,index});
  }catch(e){if(e.connection)connected=false;notice='Viewer queue: '+e.message;}
  finally{running=false;update();}
 }catch(e){notice='Viewer queue: '+e.message;update();}
 finally{viewerBusy=false;}
}
setInterval(()=>void viewerTick(),5000);
void viewerTick();
