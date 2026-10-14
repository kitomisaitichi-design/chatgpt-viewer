'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function classes(initial=[]){const values=new Set(initial);return{toggle(name,on){if(on)values.add(name);else values.delete(name);},contains(name){return values.has(name);}};}
function card(){
 const table={classList:classes()},viewport={hidden:false},toggle={textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v;}};
 const fit={textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v;}},compact={attrs:{},setAttribute(k,v){this.attrs[k]=v;}};
 const c={dataset:{},querySelector(k){return k==='table'?table:k==='.table-wrap'?viewport:k==='.table-toggle'?toggle:k==='.table-fit'?fit:k==='.table-compact'?compact:null;}};
 return{card:c,table,viewport,toggle,fit,compact};
}
const a=card(),b=card(),main={classList:classes()},document={addEventListener(){},getElementById(id){return id==='main'?main:null;},querySelectorAll(q){return q==='#messages .table-card'?[a.card,b.card]:[];}};
let saved=null;
const context={window:{},document,S:{settings:{}},saveSetting(k,v){saved=[k,v];return Promise.resolve();},toast(){throw Error('Unexpected toast');}};
vm.createContext(context);vm.runInContext(fs.readFileSync('web/table-preferences.js','utf8'),context);
const model=context.window.TablePreferences;
for(const mode of ['clean','fit','wide','compact','sleek','expanded']){
 model.setMode(mode,false);
 assert.equal(model.getMode(),mode);
 assert.equal(main.classList.contains('table-global-'+mode),true);
 for(const item of [a,b]){
  assert.equal(item.card.dataset.globalTableMode,mode);
  assert.equal(item.table.classList.contains('fit-table'),mode==='fit'||mode==='expanded');
  assert.equal(item.table.classList.contains('compact-table'),mode==='compact');
  assert.equal(item.fit.textContent,mode==='fit'||mode==='expanded'?'Wide':'Fit');
  assert.equal(item.compact.attrs['aria-pressed'],String(mode==='compact'));
 }
}
model.setAll(false);assert(a.viewport.hidden&&b.viewport.hidden);assert.equal(a.toggle.attrs['aria-expanded'],'false');
model.setAll(true);assert(!a.viewport.hidden&&!b.viewport.hidden);assert.equal(b.toggle.attrs['aria-expanded'],'true');
model.forConversation('chat-a');a.viewport.hidden=true;model.applyCard(a.card);assert.equal(a.viewport.hidden,true,'New conversation clears the global expansion override');
model.setMode('clean',true);assert.deepEqual(saved,['tableLayout','clean']);
console.log('Global table layout checks passed: all 6 modes, both tables, expand/collapse all, conversation scope and persisted preference.');
