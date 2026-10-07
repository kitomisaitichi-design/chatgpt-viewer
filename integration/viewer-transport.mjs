// Same viewer leases as the independent companion, executed by the exporter Engine.
let client=crypto.randomUUID(),busy=false,last=0;
async function post(config,op,body){const u=new URL(config.endpoint);if(u.protocol!=='http:'||!['127.0.0.1','localhost'].includes(u.hostname))throw Error('Viewer endpoint must be local');const r=await fetch(u.origin+'/api/companion/'+op,{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Connection':config.key},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('Viewer transport returned '+r.status);return r.json();}
export async function contact(engine,{root,bridge,write,index,readQueue},execute=true){
 if(busy||!root||!engine?.job?.scope||!execute&&Date.now()-last<5000)return false;
 const config=await readQueue(root,'.viewer-queue/companion.json');if(!config)return false;
 busy=true;last=Date.now();
 try{
  const body={client,kind:'exporter',connected:true,scope:engine.job.scope,connection:{attempts:0},cooldown:Math.max(engine.job.pace?.until||0,engine.job.pace?.next||0)/1000};
  // A heartbeat cannot claim a request while the Engine owns a different lane.
  const response=await post(config,'poll',{...body,heartbeat:!execute});
  if(!execute)return !!response.pending;
  if(!response.request){if(response.pending){await engine.sleep(Math.max(250,Math.min(5000,(response.wait||2)*1000)));return true;}return false;}
  const req=response.request;
  if(req.scope.user!==engine.job.scope.user||(req.scope.account||null)!==(engine.job.scope.account||null))throw Error('Viewer account does not match exporter');
  await engine.holdPoint();
  if(await engine.paceRequest('read')===false){await post(config,'result',{client,...req,result:{ok:false,status:429,retryAfter:'8'}});return true;}
  const permit=await post(config,'permit',{client,...req});
  if(!permit.allowed){await post(config,'result',{client,...req,result:{ok:false,status:409,error:'Paused before request'}});return true;}
  const result=await bridge({...req,id:req.cid,lastLimitSeen:engine.job.lastLimitSeen||0});
  if(result.status===429){const delay=Number(result.retryAfter);engine.job.pace.until=Math.max(engine.job.pace.until||0,Date.now()+(delay>0?delay*1000:60000));await engine.save();}
  const accepted=await post(config,'result',{client,...req,result});
  // The shared receipts are imported by turn() before other discovery lanes.
  if([401,403,409].includes(result.status)){const e=Error(result.error||'Reconnect ChatGPT');e.connection=true;e.name='Paused';throw e;}
  return !!accepted.accepted;
 }catch(e){if(e.connection)throw e;console.warn('Viewer connection:',e.message);return false;}
 finally{busy=false;}
}
