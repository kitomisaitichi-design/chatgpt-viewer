'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
 constructor(){this.children=[];this.value='';this.attrs={};this.open=false;this.listeners={};this.classes=new Set();this.classList={toggle:(k,v)=>v?this.classes.add(k):this.classes.delete(k)};}
 append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;this._text='';}
 set textContent(text){this._text=String(text);this.children=[];}get textContent(){return (this._text||'')+this.children.map(c=>c.textContent).join('');}
 setAttribute(k,v){this.attrs[k]=String(v);}removeAttribute(k){delete this.attrs[k];}
 scrollIntoView(){}focus(){}click(){return this.onclick?.();}addEventListener(k,fn){this.listeners[k]=fn;}close(){this.open=false;this.listeners.close?.();}
}
const ids=new Map(),element=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);},pending=[],timers=new Map(),opened=[],errors=[];let timerId=0;
const chats=[{id:'a',title:'Alpha plan',kind:'chat'},{id:'b',title:'Beta plan',kind:'work'}];
const c={window:{},URLSearchParams,AbortController,performance,Intl,S:{chats,chatById:new Map(chats.map(x=>[x.id,x])),searchGen:0},$:element,displayTitle:x=>x.alias||x.title||x.id,kind:x=>x.kind||'chat',el:(tag,cls,text)=>{const e=new Element();if(text!==undefined)e.textContent=text;return e;},safeRun:fn=>fn,openChat:async id=>opened.push(id),toast:e=>errors.push(e),setTimeout:fn=>{const id=++timerId;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),api:(url,body,options)=>new Promise((resolve,reject)=>pending.push({url,options,resolve,reject}))};
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/catalog-model.js'),'utf8'),c);c.CatalogModel=c.window.CatalogModel;
const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');vm.runInContext(app.slice(app.indexOf('let archiveResults='),app.indexOf('function updateRescanLabel')),c);
for(const line of app.split('\n'))if(line.includes("$('search-query').onkeydown=e=>")||line.includes("$('search-clear').onclick="))vm.runInContext(line,c);
element('search-dialog').open=true;element('search-mode').value='title';element('search-type').value=element('search-category').value='all';element('search-sort').value='rank';
const type=q=>{element('search-query').value=q;c.scheduleSearch();};
const dispatch=()=>{const [id,fn]=[...timers][0];timers.delete(id);fn();};
(async()=>{
 type('alpha');assert(element('search-results').textContent.includes('Alpha plan'),'Local title result is visible before any request');assert.equal(pending.length,0);
 dispatch();assert(pending[0].url.includes('mode=title'));type('beta');assert(pending[0].options.controller.signal.aborted,'Typing cancels the old request');
 pending[0].resolve({results:[{cid:'a',seq:-1,title:'Alpha plan'}],mode:'titles'});await new Promise(setImmediate);assert(!element('search-results').textContent.includes('Alpha plan'),'Late response cannot replace the new query');
 dispatch();pending[1].resolve({results:[{cid:'b',seq:-1,title:'Beta plan'}],mode:'titles'});await new Promise(setImmediate);
 element('search-query').onkeydown({key:'Enter',preventDefault(){}});element('search-query').onkeydown({key:'Enter',preventDefault(){}});assert.deepEqual(opened,['b'],'Repeated Enter opens one matching title');
 element('search-dialog').open=true;type('unloaded');dispatch();pending[2].resolve({results:[{cid:'not-yet-listed',seq:-1,title:'Unloaded saved title'}],mode:'titles'});await new Promise(setImmediate);assert(element('search-results').textContent.includes('Unloaded saved title'),'Metadata lookup covers an incomplete client catalog');
 element('search-clear').click();assert.equal(element('search-query').value,'');assert.equal(timers.size,0);assert.equal(element('search-clear').hidden,true);
 type('alpha');dispatch();element('search-dialog').close();pending[3].reject(Error('Delayed network failure'));await new Promise(setImmediate);assert.equal(errors.length,0,'Closing search cancels stale error feedback');
 console.log('Fast title UI: immediate local hits, metadata fallback, stale-response cancellation, Enter/double-submit, clear and close passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
