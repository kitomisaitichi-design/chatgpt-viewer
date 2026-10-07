import {turn,heartbeat,readQueue} from './viewer-delete-adapter.mjs';
// Connect retry budget is persistent; cooldown/rate-limit retries remain Engine-owned.
export async function connectionState({db,root,scope,connect,write,sleep,manual=false}){
 const key=`viewerConnection:${scope.key}`,reset=await readQueue(root,'.viewer-queue/reconnect.json');
 let state=await db.get('meta',key)||{attempts:0,nonce:'',blocked:false};
 if(manual||state.nonce!==(reset?.nonce||''))state={attempts:0,nonce:reset?.nonce||'',blocked:false};
 if(state.blocked)return false;
 // Initial attempt plus at most two retries, then explicit reconnect is required.
 for(;state.attempts<3;){
  state.attempts++;await db.put('meta',key,state);
  try{await connect();state={attempts:0,nonce:state.nonce,blocked:false,authenticatedAt:Date.now()/1000};await db.put('meta',key,state);return true;}
  catch(error){state.error=error.message;state.blocked=state.attempts>=3;await db.put('meta',key,state);await heartbeat({root,job:{scope},canEdit:true,connected:false,write,connection:state});if(state.blocked)return false;await sleep(5000);}
 }
 return false;
}
export async function drain(Engine,job,io,{root,bridge,write,index},shouldStop=()=>false){
 const engine=new Engine(job,io);let count=0,beating=false,heartbeatError=null;
 const beat=async()=>{if(beating)return;beating=true;try{await heartbeat({root,job,canEdit:true,connected:true,write,connection:await io.connection?.()||{}});}catch(e){heartbeatError=e;}finally{beating=false;}};
 const timer=setInterval(()=>void beat(),5000);
 try{
 while(!shouldStop()){
  if(heartbeatError)throw heartbeatError;
  await engine.holdPoint();
  if(!await turn(engine,{root,bridge,write,index}))break;
  count++;await new Promise(r=>setTimeout(r,0));
 }
 return count;
 }finally{clearInterval(timer);}
}
