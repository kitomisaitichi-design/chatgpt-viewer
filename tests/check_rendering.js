const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const web=path.join(__dirname,'../web'),context={};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(web,'chart-math.js'),'utf8'),context);
const math=context.ChartMath,rows=Array.from({length:100000},(_,i)=>({x:i,value:Math.sin(i/40)}));rows[87654].value=9999;rows[55555].value=-5000;rows[67890].value=null;
const range=math.extent(rows.map(r=>r.value));assert.equal(range.max,9999);assert.equal(range.min,-5000);
const sampled=Array.from(math.samples(rows,'value'));assert(sampled.includes(99999));assert(sampled.includes(87654));assert(sampled.includes(55555));assert(sampled.includes(67890));assert(sampled.length<1700);
for(const [value,index] of [[0,0],[2,1],[3.9,2],[100,3]])assert.equal(math.nearest([0,2,4,100],value),index);
assert.equal(math.finite(null),false);assert.equal(math.finite(''),false);assert.equal(math.finite(0),true);
// Run the real bundled parser and worker with message transport simulated.
const messages=[],worker={postMessage:m=>messages.push(m),setTimeout,clearTimeout,AbortController,URL:{createObjectURL:b=>b.text,revokeObjectURL(){}},Blob:class{constructor(parts){this.text=parts.join('');}},fetch:async()=>({ok:true,text:async()=>fs.readFileSync(path.join(web,'vendor/marked.js'),'utf8')})};
vm.createContext(worker);worker.importScripts=text=>vm.runInContext(text,worker);vm.runInContext(fs.readFileSync(path.join(web,'render-worker.js'),'utf8'),worker);
(async()=>{await new Promise(resolve=>setImmediate(resolve));assert(messages.some(m=>m.ready));const markdown='| A | B |\n| --- | --- |\n| **bold** | 123 |\n\n```python\nprint(1)\n```';
 await worker.onmessage({data:{id:1,text:markdown}});assert(messages.at(-1).html.includes('<table>'));assert(messages.at(-1).html.includes('language-python'));const html=messages.at(-1).html;
 worker.marked.lexer=()=>{throw Error('Unexpected parse of cached message');};await worker.onmessage({data:{id:2,text:markdown}});assert.equal(messages.at(-1).html,html);
 await worker.onmessage({data:{id:3,mode:'code',language:'json',text:'{"large":9007199254740993,"name":"hi"}'}});assert(messages.at(-1).html.includes('9007199254740993'));assert(!messages.at(-1).error);
 console.log('Chart extrema/gaps/nearest-point and actual Markdown worker cache checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
