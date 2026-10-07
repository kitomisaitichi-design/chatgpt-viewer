import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';
const state={config:{endpoint:'http://127.0.0.1:23456',key:'private-test-key'},client:'test',connection:{attempts:0,nonce:'initial'}};
let connects=0,nonce='initial';
const context={crypto,URL,AbortSignal,console,setTimeout:()=>1,clearTimeout:()=>{},fetch:async url=>({ok:!String(url).includes('pairing.json'),json:async()=>({nonce,wait:15})}),chrome:{storage:{local:{get:async()=>structuredClone(state),set:async values=>Object.assign(state,structuredClone(values))}},tabs:{query:async()=>[{id:1,active:true}]},scripting:{executeScript:async()=>{connects++;return [{result:{ok:false,status:401,error:'Sign in'}}];}},runtime:{getURL:path=>'extension:///'+path,onMessage:{addListener(){}},onStartup:{addListener(){}},onInstalled:{addListener(){}}},alarms:{create(){},onAlarm:{addListener(){}}}}};
vm.createContext(context);
const source=fs.readFileSync(new URL('../integration/browser-companion/background.js',import.meta.url),'utf8');
vm.runInContext(source.replace(/void tick\(\);\s*$/,''),context);
for(let n=0;n<5;n++){state.connection.nextAt=0;await vm.runInContext('tick()',context);}
assert.equal(connects,3);assert.equal(state.connection.blocked,true);assert.equal(state.connection.attempts,3);
nonce='manual-reconnect';state.connection.nextAt=0;await vm.runInContext('tick()',context);
assert.equal(connects,4);assert.equal(state.connection.attempts,1);assert.equal(state.connection.blocked,false);
for(const file of ['background.js','bridge.js','popup.js'])new Function(fs.readFileSync(new URL('../integration/browser-companion/'+file,import.meta.url),'utf8'));
console.log('Browser connection: initial attempt plus two retries; restart budget and manual reconnect checked with simulated browser APIs.');
