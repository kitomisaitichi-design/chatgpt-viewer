// Contract test against a real, patched exporter folder. HTTP is simulated; no account changes.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const folder=path.resolve(process.argv[2]);
const {turn,pending}=await import(pathToFileURL(path.join(folder,'viewer-delete-adapter.mjs')));
const {Engine}=await import(pathToFileURL(path.join(folder,'engine.mjs')));
const {newJob,mergeEntry}=await import(pathToFileURL(path.join(folder,'core.mjs')));
const base=await fs.mkdtemp(path.join(os.tmpdir(),'viewer-delete-contract-'));
class Directory{
 constructor(p){this.path=p;}
 async getDirectoryHandle(n,{create=false}={}){const p=path.join(this.path,n);try{if(create)await fs.mkdir(p,{recursive:true});await fs.access(p);}catch(e){if(e.code==='ENOENT')e.name='NotFoundError';throw e;}return new Directory(p);}
 async getFileHandle(n){const p=path.join(this.path,n);try{await fs.access(p);}catch(e){if(e.code==='ENOENT')e.name='NotFoundError';throw e;}return {getFile:async()=>({size:(await fs.stat(p)).size,text:()=>fs.readFile(p,'utf8')})};}
 async *values(){for(const d of await fs.readdir(this.path,{withFileTypes:true}))yield {name:d.name,kind:d.isDirectory()?'directory':'file'};}
}
const schema='offline-viewer/delete-v1',scope={key:'user:workspace',user:'user',account:'workspace'},cid='12345678-1234-1234-1234-123456789abc';
let cases=0;
async function fixture(name){const p=path.join(base,name);await fs.mkdir(p);const root=new Directory(p),write=async(n,value)=>{const target=path.join(p,n);await fs.mkdir(path.dirname(target),{recursive:true});await fs.writeFile(target,value);};
 const command={schema,id:'a'.repeat(32),cid,scope:scope.key,run:'run-1',mode:'preserve',content_hash:'unchanged-hash'};
 await write('.viewer-queue/control.json',JSON.stringify({schema,enabled:true,updated:Date.now()/1000,run:command.run}));await write('.viewer-queue/commands/'+command.id+'.json',JSON.stringify(command));
 const job=newJob(scope,{attachments:false,library:false,verify:false});job.entries[cid]={id:cid,status:'saved',contentHash:'unchanged-hash',title:'Fixture'};let now=Date.now(),saves=0;
 const engine=new Engine(job,{save:async()=>{saves++;},now:()=>now,sleep:async ms=>{now+=ms;},changed:()=>{}});const receipt=async()=>JSON.parse(await fs.readFile(path.join(p,'.viewer-queue/receipts/'+command.id+'.json'),'utf8'));
 return {p,root,write,job,engine,command,receipt,index:async()=>{},saves:()=>saves};}
try{
 let f=await fixture('serial-rate-limit'),calls=[];let visible=true,limited=false;
 const bridge=async args=>{calls.push(args.op);if(!limited){limited=true;return {ok:false,status:429,retryAfter:'1'};}if(args.op==='viewerDelete'){visible=false;return {ok:true,status:200};}return {ok:true,status:200,data:{is_visible:visible}};};
 assert.equal(await pending(f.root,scope.key),true);assert.equal(await turn(f.engine,{...f,bridge}),true);assert.deepEqual(calls,['get','get','viewerDelete','get']);assert.equal((await f.receipt()).verified,true);assert.equal(f.job.entries[cid].contentHash,'unchanged-hash');assert.equal(f.job.entries[cid].status,'viewer-deleted');assert.ok(f.job.pace.tier>0);assert.ok(f.saves()>2);assert.equal(await pending(f.root,scope.key),false);await turn(f.engine,{...f,bridge});assert.equal(calls.length,4);cases++;
 mergeEntry(f.job,{id:cid,title:'Reappearing hint',update_time:Date.now()});assert.equal(f.job.entries[cid].status,'viewer-deleted');await f.engine.reconcileInventory([{id:cid,diskBacked:true,validated:true,contentHash:'unchanged-hash'}]);assert.equal(f.job.entries[cid].status,'viewer-deleted');cases++;
 f=await fixture('wrong-account');f.command.scope='different';await f.write('.viewer-queue/commands/'+f.command.id+'.json',JSON.stringify(f.command));let touched=false;assert.equal(await turn(f.engine,{...f,bridge:async()=>{touched=true;}}),false);assert.equal(touched,false);cases++;
 f=await fixture('pause-before-write');calls=[];await turn(f.engine,{...f,bridge:async args=>{calls.push(args.op);await f.write('.viewer-queue/control.json',JSON.stringify({schema,enabled:false,run:'run-1'}));return {ok:true,status:200,data:{is_visible:true}};}});assert.deepEqual(calls,['get']);assert.equal((await f.receipt()).state,'paused');cases++;
 f=await fixture('uncertain-request-recovery');calls=[];await turn(f.engine,{...f,bridge:async args=>{calls.push(args.op);return {ok:false,status:404};}});assert.deepEqual(calls,['get']);assert.equal((await f.receipt()).state,'confirmed');cases++;
 f=await fixture('unconfirmed');await turn(f.engine,{...f,bridge:async()=>({ok:true,status:200,data:{is_visible:true}})});assert.equal((await f.receipt()).state,'failed');assert.equal(f.job.viewerDeletes?.[cid],undefined);cases++;
 f=await fixture('updated-while-waiting');calls=[];await turn(f.engine,{...f,bridge:async args=>{calls.push(args.op);f.job.entries[cid].refresh=true;return {ok:true,status:200,data:{is_visible:true}};}});assert.deepEqual(calls,['get']);assert.equal((await f.receipt()).state,'failed');cases++;
 f=await fixture('expired-control');calls=[];await f.write('.viewer-queue/control.json',JSON.stringify({schema,enabled:true,updated:Date.now()/1000-60,run:'run-1'}));assert.equal(await pending(f.root,f.job.scope.key),false);await turn(f.engine,{...f,bridge:async a=>{calls.push(a);return {ok:true};}});assert.equal(calls.length,0);cases++;
 console.log(cases+' exporter adapter contract cases passed (simulated HTTP, real exporter gate/pacing).');
}finally{await fs.rm(base,{recursive:true,force:true});}
