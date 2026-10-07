const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
class Element {
 constructor(){this.children=[];this.isConnected=true;this.classList={remove(){},add(){}};this.parentElement={};}
 setAttribute(k,v){this[k]=v;} append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;}
}
let observed,observe,requests=[];
const state={selected:{id:'one'},leaf:null,chatById:new Map()};
const context={window:{},document:{getElementById(){return {};},createElement(){return new Element();},addEventListener(){}},IntersectionObserver:class{constructor(fn){observe=fn;}observe(host){observed=host;}unobserve(){}},S:state,URLSearchParams,Map,Set,Date,addEventListener(){},api:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/thread-attachments.js'),'utf8'),context);
const preview=context.window.ThreadAttachments,tick=()=>new Promise(resolve=>setImmediate(resolve));
async function run(){
 const first=preview.catalog('one',null),second=preview.catalog('one',null,true);assert.strictEqual(first,second);assert.equal(requests.length,1);requests[0].resolve({attachments:[],last_seq:4});await first;
 const article={querySelector(){return {prepend(){}};}};state.selected={id:'two'};preview.mount(article,{seq:4},'two',null);const host=observed;observe([{target:host,isIntersecting:true}]);requests[1].reject(Error('Metadata unavailable'));await tick();assert.equal(host.children[0].textContent,'Retry loading attachments');assert.equal(host.children[1].textContent,'Metadata unavailable');host.children[0].onclick();assert.equal(requests.length,3);requests[2].resolve({attachments:[],last_seq:4});await tick();assert.equal(host.hidden,true);
 state.selected={id:'three'};preview.mount(article,{seq:4},'three',null);const stale=observed;observe([{target:stale,isIntersecting:true}]);state.selected={id:'four'};requests[3].reject(Error('Stale request'));await tick();assert.equal(stale.children.length,0);
 const X=require('../web/vendor/documents/xlsx/xlsx.full.min.js'),book=X.utils.book_new();X.utils.book_append_sheet(book,X.utils.aoa_to_sheet([['Name','Value'],['<script>literal</script>',42]]),'First');X.utils.book_append_sheet(book,X.utils.aoa_to_sheet([['Other'],['Lighthouse']]),'Second');let reply;const worker={XLSX:X,importScripts(){},postMessage(value){reply=value;}};vm.createContext(worker);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/sheet-worker.js'),'utf8'),worker);worker.onmessage({data:{id:1,action:'load',buffer:X.write(book,{type:'array',bookType:'xlsx'})}});assert.deepEqual(Array.from(reply.names),['First','Second']);worker.onmessage({data:{id:2,action:'page',name:'First',offset:0}});assert.equal(reply.rows[1][0],'<script>literal</script>');worker.onmessage({data:{id:3,action:'search',name:'Second',query:'lighthouse'}});assert.equal(reply.match,1);
 console.log('Attachments: coalesced metadata, retry, stale isolation, workbook sheets, literal cells and search passed.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
