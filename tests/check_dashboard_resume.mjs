import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const app=fs.readFileSync(process.argv[2],'utf8');
const extract=(name,next)=>app.slice(app.indexOf('async function '+name+'('),app.indexOf(next,app.indexOf('async function '+name+'(')));
const picked={name:'parent',queryPermission:async()=> 'granted',isSameEntry:async h=>h===picked};
const canonical={name:'backup',queryPermission:async()=> 'granted',isSameEntry:async h=>h===canonical};
let scans=0,merged=0,heartbeats=0;
const context=vm.createContext({console,URLSearchParams,Date,setInterval:()=>{},clearInterval:()=>{},
 canEdit:true,initializing:false,starting:false,detecting:false,connecting:false,running:false,connected:true,folder:picked,root:null,rootDetection:null,
 scope:{key:'account'},job:{scope:{key:'account'},entries:{}},backupInput:null,notice:'',localSummary:'',locations:[],diskFiles:new Map(),diskScanStats:{},
 db:{get:async()=>({nonce:'',attempts:0,blocked:false}),put:async()=>{},cacheInventory:async()=>[]},update:()=>{},beginDetection:()=>{},endDetection:()=>{},
 resolveBackupFolder:async()=>{scans++;return {root:canonical,metadata:{index:{entries:[]},state:null}};},rememberLocation:async()=>{},
 mergeFolderMetadata:(_j,m)=>{assert.ok(m);merged++;},migrateLoadedJob:()=>{},diskInventory:async()=>[],
 appendEvent:()=>{},newJob:()=>({entries:{}}),Engine:class{async reconcileInventory(){}},applyJobOptionsToUI:()=>{},
 viewerQueue:{readQueue:async()=>null,pending:async()=>false,heartbeat:async({root,write})=>{assert.ok(root);await write();heartbeats++;}},
 bridge:async()=>({ok:true,scope:{user:'fixture'}}),digest:async()=> 'account',
});
vm.runInContext(extract('folderReady','async function detectLocalState')+extract('detectLocalState','async function write')+
 'async function write(){if(!root)await folderReady(false);}\n'+app.slice(app.indexOf('// Viewer queue adapter v2:')).replace(/void viewerTick\(\);\s*$/,''),context);
await vm.runInContext('viewerTick()',context);
assert.equal(context.notice,'','Heartbeat must not swallow a fixture/runtime error');
await vm.runInContext('detectLocalState()',context);
assert.equal(merged,1);assert.equal(scans,1);assert.equal(heartbeats,1);
assert.equal(context.root,canonical);assert.equal(context.rootDetection.root,canonical);
// A second heartbeat must reuse resolved metadata rather than scan or reset it.
await vm.runInContext('viewerTick();',context);assert.equal(scans,1);
// Repair an old in-memory root with absent metadata instead of silently skipping detection.
context.rootDetection=null;await vm.runInContext('detectLocalState()',context);
assert.equal(scans,2);assert.equal(merged,2);
console.log('PASS: heartbeat → resume, nested root resolution, cached reuse, stale root recovery');
