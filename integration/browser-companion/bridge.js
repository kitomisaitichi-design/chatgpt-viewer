// Authentication stays in the ChatGPT page. Only scoped operations are exposed.
(() => {
 if(window.__offlineViewerConnection)return;
 const fetchOriginal=window.fetch.bind(window),cookie=name=>{const v=document.cookie.split('; ').find(s=>s.startsWith(name+'='))?.slice(name.length+1);try{return v?decodeURIComponent(v):null;}catch{return null;}};
 let token=null,user=null,account=null,selector=null,sessionAt=0,inFlight=0,lastStart=0,cooldown=0,activeStreams=0;
 const selected=()=>{const c=cookie('_account');return c==='personal'&&selector===c&&account?account:c||account||null;};
 const scope=()=>({user,account:selected()});
 window.fetch=async function(resource,options){
  let url;try{url=new URL(typeof resource==='string'||resource instanceof URL?resource:resource.url,location.href);}catch{}
  const internal=url?.origin===location.origin&&url.pathname.startsWith('/backend-api/');
  if(internal){const h=new Headers(resource instanceof Request?resource.headers:undefined);new Headers(options?.headers).forEach((v,k)=>h.set(k,v));const auth=h.get('authorization');if(auth?.startsWith('Bearer ')&&auth!=='Bearer dummy')token=auth.slice(7);if(h.has('chatgpt-account-id')){account=h.get('chatgpt-account-id');selector=cookie('_account');}inFlight++;lastStart=Date.now();}
  try{const r=await fetchOriginal(resource,options);if(internal&&r.status===429){const n=Number(r.headers.get('retry-after'));cooldown=Math.max(cooldown,Date.now()+(n>0?n*1000:60000));}if(internal&&r.headers.get('content-type')?.includes('text/event-stream')&&r.body){activeStreams++;const reader=r.clone().body.getReader();void(async()=>{try{while(!(await reader.read()).done){}}catch{}finally{activeStreams--;reader.releaseLock();lastStart=Date.now();}})();}return r;}finally{if(internal)inFlight--;}
 };
 async function authenticate(force=false){
  if(user&&token&&!force&&Date.now()-sessionAt<45000)return;
  const r=await fetchOriginal('/api/auth/session',{credentials:'include',signal:AbortSignal.timeout(30000)});
  if(!r.ok)throw Object.assign(Error('ChatGPT session returned '+r.status),{status:r.status});
  const d=await r.json();if(!d?.user?.id||!d.accessToken)throw Object.assign(Error('Sign in to ChatGPT in this tab'),{status:401});
  if(user&&user!==d.user.id){account=null;selector=null;}user=d.user.id;token=d.accessToken;sessionAt=Date.now();
 }
 const matches=s=>s?.user===user&&(s.account||null)===selected();
 async function rpc(a){try{
  await authenticate(a.force===true);
  if(a.op==='context')return {ok:true,scope:scope(),cooldown:cooldown/1000};
  if(!matches(a.scope))return {ok:false,status:409,error:'The ChatGPT account/workspace changed; reconnect and review'};
  if(!/^[a-zA-Z0-9_-]{8,160}$/.test(a.cid||a.id||'')||!['get','viewerDelete'].includes(a.op))return {ok:false,status:400,error:'Unsupported viewer request'};
  const now=Date.now();
  if(cooldown>now)return {ok:false,status:429,retryAfter:String(Math.ceil((cooldown-now)/1000)),error:'ChatGPT rate limit in this tab'};
  const wait=(inFlight||activeStreams)?now+8000:lastStart+8000;
  // Waiting for the user's own ChatGPT activity is NOT an HTTP 429.
  // A real 429 must be reported separately so the viewer doesn't turn every
  // brief local pacing delay into a durable, global rate-limit cooldown.
  if(wait>now)return {ok:false,status:0,localPacing:true,retryAfter:String(Math.ceil((wait-now)/1000)),error:'Waiting for active ChatGPT traffic'};
  const headers={authorization:'Bearer '+token,accept:'application/json','content-type':'application/json','oai-language':'en-US'};
  const device=cookie('oai-did');if(device){headers['oai-device-id']=device;headers['oai-did']=device;}if(a.scope.account)headers['chatgpt-account-id']=a.scope.account;
  lastStart=Date.now();
  // Each verification must be a fresh authenticated network read, never a
  // browser-cache replay of the first missing response.
  const r=await fetchOriginal('/backend-api/conversation/'+encodeURIComponent(a.cid||a.id),{method:a.op==='viewerDelete'?'PATCH':'GET',headers,credentials:'include',...(a.op==='viewerDelete'?{body:JSON.stringify({is_visible:false})}:{cache:'no-store'}),signal:AbortSignal.timeout(60000)});
  if(r.status===401){token=null;sessionAt=0;}
  if(!matches(a.scope))return {ok:false,status:409,error:'Workspace changed during request'};
  const retryAfter=r.headers.get('retry-after');if(r.status===429)cooldown=Date.now()+(Number(retryAfter)>0?Number(retryAfter)*1000:60000);
  if(!r.ok)return {ok:false,status:r.status,retryAfter};
  if(a.op==='viewerDelete')return {ok:true,status:r.status};
  if(!r.headers.get('content-type')?.includes('json'))return {ok:false,status:403,error:'Finish the browser check in ChatGPT, then reconnect'};
  return {ok:true,status:r.status,data:await r.json()};
 }catch(e){return {ok:false,status:e.status||0,error:e.message};}}
 Object.defineProperty(window,'__offlineViewerConnection',{value:{rpc},writable:false});
})();
