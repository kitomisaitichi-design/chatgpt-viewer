import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

let clock=100000,remoteLimit=false,remoteCalls=0,remoteOptions=[];
class Clock extends Date {static now(){return clock;}}
const origin='https://chatgpt.com';
const window={
  fetch:async function(resource,options={}){
    const url=new URL(typeof resource==='string'?resource:resource.url,origin);
    if(url.pathname==='/api/auth/session')
      return {ok:true,json:async()=>({user:{id:'user-for-test'},accessToken:'test-token'})};
    if(url.pathname.startsWith('/backend-api/conversation/')){
      remoteCalls++;
      remoteOptions.push(options);
      if(remoteLimit)return {status:429,ok:false,headers:new Headers({'retry-after':'60'})};
      return {status:200,ok:true,headers:new Headers({'content-type':'application/json'}),json:async()=>({mapping:{}})};
    }
    return {status:200,ok:true,headers:new Headers()};
  }
};
const context={window,document:{cookie:''},location:{origin,href:origin+'/'},URL,Request,Headers,AbortSignal,Date:Clock};
const source=readFileSync(new URL('../integration/browser-companion/bridge.js',import.meta.url),'utf8');
runInNewContext(source,context);
const scope={user:'user-for-test',account:null},cid='12345678-1234-1234-1234-123456789abc';
await window.fetch('/backend-api/other-traffic');
const local=await window.__offlineViewerConnection.rpc({op:'get',cid,scope});
assert.equal(local.localPacing,true);
assert.equal(local.status,0);
assert.equal(local.retryAfter,'8');
assert.equal(remoteCalls,0);
clock+=9000;
remoteLimit=true;
const limited=await window.__offlineViewerConnection.rpc({op:'get',cid,scope});
assert.equal(limited.status,429);
assert.notEqual(limited.localPacing,true);
assert.equal(limited.retryAfter,'60');
assert.equal(remoteCalls,1);
assert.equal(remoteOptions[0].cache,'no-store','Authenticated conversation checks must bypass browser cache');
const stillLimited=await window.__offlineViewerConnection.rpc({op:'get',cid,scope});
assert.equal(stillLimited.status,429);
assert.notEqual(stillLimited.localPacing,true);
assert.equal(remoteCalls,1);
console.log('Browser pacing stays local; actual ChatGPT 429 retains its Retry-After.');
