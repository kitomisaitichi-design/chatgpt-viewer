const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
class Element {
 constructor(){this.children=[];this.isConnected=true;this.classList={remove(){},add(){}};this.parentElement={};}
 setAttribute(k,v){this[k]=v;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
}
let observed,callback,requests=[];
const state={selected:{id:'one'},leaf:null,chatById:new Map()};
const context={window:{},document:{getElementById(){return {};},createElement(){return new Element();},createTreeWalker(){return {nextNode(){return false;}};},addEventListener(){}},NodeFilter:{SHOW_TEXT:4},IntersectionObserver:class{constructor(fn){callback=fn;}observe(host){observed=host;}unobserve(){}},S:state,URLSearchParams,Map,Set,api:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/thread-images.js'),'utf8'),context);
const gallery=context.window.ThreadImages,body={prepend(){}},article={querySelector(){return body;}},tick=()=>new Promise(resolve=>setImmediate(resolve));
async function run(){
 gallery.mount(article,{seq:4},'one',null);const host=observed;callback([{target:host,isIntersecting:true}]);requests[0].reject(Error('Catalog timeout'));await tick();
 assert.equal(host.children[0].textContent,'Retry loading images');assert.equal(host.children[1].textContent,'Catalog timeout');assert.equal(host.children[1].role,'status');
 host.children[0].onclick();assert.equal(host.children[0].disabled,true);assert.equal(requests.length,2);requests[1].resolve({images:[],last_seq:4});await tick();assert.equal(host.hidden,true);
 state.selected={id:'two'};gallery.mount(article,{seq:4},'two',null);const stale=observed;callback([{target:stale,isIntersecting:true}]);state.selected={id:'three'};requests[2].reject(Error('Old chat failed'));await tick();assert.equal(stale.children.length,0);
 const first=gallery.catalog('three',null),second=gallery.catalog('three',null);assert.strictEqual(first,second);assert.equal(requests.length,4);requests[3].resolve({images:[],last_seq:null});await first;
 console.log('Thread images: visible errors, guarded retry, stale failure isolation and request coalescing passed.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
