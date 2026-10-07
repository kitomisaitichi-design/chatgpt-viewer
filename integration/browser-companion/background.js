let busy=false,timer;
const local=chrome.storage.local;
async function send(config,op,data){const r=await fetch(config.endpoint+'/api/companion/'+op,{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Connection':config.key},body:JSON.stringify(data),signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('Viewer connection returned '+r.status);return r.json();}
async function page(tabId,args){const result=await chrome.scripting.executeScript({target:{tabId},world:'MAIN',func:async a=>window.__offlineViewerConnection?await window.__offlineViewerConnection.rpc(a):{ok:false,status:0,error:'Refresh this ChatGPT tab once to load the viewer connection'},args:[args]});return result[0]?.result||{ok:false,status:0,error:'ChatGPT tab is unavailable'};}
async function tick(){
 if(busy)return;busy=true;let wait=15000;
 try{
  let {config,client,connection={attempts:0}}=await local.get(['config','client','connection']);
  try{const paired=await fetch(chrome.runtime.getURL('pairing.json'),{cache:'no-store'});if(paired.ok){const automatic=await paired.json();if(!config||automatic.key===config.key)config=automatic;}}catch{}
  if(!config)return;
  if(!client){client=crypto.randomUUID();await local.set({client});}
  const hello=await send(config,'poll',{client,kind:'companion',connected:false,connection});
  if(connection.nonce!==hello.nonce){connection={attempts:0,nonce:hello.nonce};await local.set({connection});}
  if(connection.blocked)return;
  if(connection.nextAt>Date.now()){wait=Math.min(15000,connection.nextAt-Date.now());return;}
  const tabs=await chrome.tabs.query({url:'https://chatgpt.com/*'});
  const chosen=tabs.find(t=>t.id===connection.tab)||tabs.find(t=>t.active)||tabs[0];
  let context=chosen?await page(chosen.id,{op:'context'}):{ok:false,error:'Open a signed-in ChatGPT tab, then click Reconnect in the viewer'};
  if(!context.ok){connection.attempts=(connection.attempts||0)+1;connection.error=context.error;connection.blocked=connection.attempts>=3;connection.nextAt=Date.now()+5000*2**(connection.attempts-1);await local.set({connection});await send(config,'poll',{client,kind:'companion',connected:false,connection});wait=5000;return;}
  if(connection.scope&&JSON.stringify(connection.scope)!==JSON.stringify(context.scope)){connection.blocked=true;connection.error='Account/workspace changed. Reconnect in the viewer to review the new account.';await local.set({connection});await send(config,'poll',{client,kind:'companion',connected:false,connection});return;}
  Object.assign(connection,{attempts:0,blocked:false,error:'',tab:chosen.id,scope:context.scope,nextAt:0});await local.set({connection});
  const response=await send(config,'poll',{client,kind:'companion',connected:true,scope:context.scope,connection,cooldown:context.cooldown});
  wait=Math.max(1000,Math.min(15000,(response.wait||15)*1000));
  if(!response.request)return;
  const request=response.request;
  const permit=await send(config,'permit',{client,...request});
  const result=permit.allowed?await page(chosen.id,request):{ok:false,status:409,error:'Queue paused before the request'};
  await send(config,'result',{client,...request,result});wait=1500;
  if([401,403,409].includes(result.status)){connection.attempts++;connection.error=result.error||'Reconnect to ChatGPT';connection.nextAt=Date.now()+5000;connection.blocked=connection.attempts>=3;await local.set({connection});}
 }catch(e){await local.set({lastError:e.message});}
 finally{busy=false;clearTimeout(timer);timer=setTimeout(()=>void tick(),wait);}
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{if(message.op==='wake'){void tick();reply({ok:true});}});
chrome.alarms.create('viewer-connect',{periodInMinutes:.5});chrome.alarms.onAlarm.addListener(a=>{if(a.name==='viewer-connect')void tick();});
chrome.runtime.onStartup.addListener(()=>void tick());chrome.runtime.onInstalled.addListener(()=>void tick());void tick();
