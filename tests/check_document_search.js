const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/document-search.js'),'utf8'),context);const search=context.DocumentSearch;
const find=(text,q,options={})=>search.match([{text}],q,options);
assert.equal(find('Anchor anchor Anchored anchor','anchor').hits.length,4);
assert.equal(find('Anchor anchor Anchored anchor','anchor',{wholeWord:true}).hits.length,3);
assert.equal(find('Anchor anchor Anchored anchor','anchor',{caseSensitive:true,wholeWord:true}).hits.length,2);
assert.equal(find('café décafé café','café',{wholeWord:true}).hits.length,2);
assert.equal(find('a+b aaab a+b','a+b').hits.length,2);
assert.equal(find('a+b aaab a+b','a+b',{regex:true}).hits.length,1);
assert.throws(()=>find('sample','[',{regex:true}),/Invalid regular expression/);
assert.equal(find('aaa','(?=a)',{regex:true}).hits.length,0);
assert.equal(find('aaaa','a*',{regex:true}).hits.length,1);
assert.equal(find('missing','absent').hits.length,0);
assert.equal(find('abc','').hits.length,0);
assert.throws(()=>find('a','a'.repeat(501)),/500 characters/);
const cap=find('x '.repeat(10005),'x');assert.equal(cap.hits.length,10000);assert(cap.limited);
assert.equal(search.match([{text:'page one'},{text:'page two one'}],'one').hits[1].segment,1);
// Drive the actual panel controller: each Find/Enter advances, a closed
// session clears state, and no late worker response can reopen the panel.
class Element{constructor(tag){this.tagName=tag;this.children=[];this.hidden=false;this.value='';this.attrs={};}append(...n){this.children.push(...n);}setAttribute(k,v){this.attrs[k]=v;}addEventListener(){}focus(){}}
const created=[],reveals=[];let sourceReads=0,workerStarts=0;
const ui={window:{},document:{createElement(tag){const e=new Element(tag);created.push(e);return e;}},ViewerIcons:{svg(){return new Element('svg');}},setTimeout,clearTimeout,Worker:class{constructor(){workerStarts++;}postMessage(data){setImmediate(()=>this.onmessage({data:search.match(data.segments,data.query,data.options)}));}terminate(){}}};vm.createContext(ui);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/attachment-finder.js'),'utf8'),ui);
const panel=ui.window.AttachmentFinder.create(new Element('div'),{source:async()=>{sourceReads++;return {segments:[{text:'one One someone one'}]};},reveal:async(s,h,hits,index,all)=>reveals.push({offset:h.start,index,all}),clear(){}});
const input=created.find(e=>e.tagName==='input'),findButton=created.find(e=>e.textContent==='Find'),count=created.find(e=>e.className==='attachment-find-count');
async function run(){input.value='one';await findButton.onclick();assert.equal(count.textContent,'1 of 4');await findButton.onclick();assert.equal(count.textContent,'2 of 4');assert.equal(sourceReads,1);assert.equal(workerStarts,1);assert.deepEqual(reveals.map(r=>r.offset),[0,4]);await panel.search();await panel.search();await panel.search();assert.equal(count.textContent,'1 of 4');assert.equal(panel.panel.hidden,false);
 const whole=created.find(e=>e.attrs['aria-label']==='Whole word');whole.onclick();await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));assert.equal(count.textContent,'1 of 3');
 const all=created.find(e=>e.attrs['aria-label']==='Highlight all');all.onclick();await new Promise(r=>setImmediate(r));assert.equal(reveals.at(-1).all,false);
 panel.reset();assert.equal(panel.panel.hidden,true);assert.equal(input.value,'');assert.equal(count.textContent,'0 of 0');
 input.value='one';const pending=panel.search();panel.reset();await pending;assert.equal(panel.panel.hidden,true);assert.equal(count.textContent,'0 of 0');
 console.log('Document finder: literal/regex/Unicode/word/case options, invalid and empty patterns, result cap, match traversal, wrap, cached source, highlight toggle and stale-close cancellation passed.');}
run().catch(error=>{console.error(error);process.exitCode=1;});
