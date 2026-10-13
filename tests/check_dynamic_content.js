'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
// Minimal DOM exercises the actual control handlers without a browser dependency.
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.dataset={};this.style={setProperty:(k,v)=>this.style[k]=v};this.classes=new Set();this.classList={add:(...c)=>c.forEach(x=>this.classes.add(x))};this._text='';}
 set textContent(v){this._text=String(v);this.children=[];}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;this._text='';}
 setAttribute(k,v){this.attributes[k]=String(v);}
 getAttribute(k){return this.attributes[k];}
 removeAttribute(k){delete this.attributes[k];}
 focus(){this.focused=true;}
}
const writes=[],toasts=[];let pending=null,rejectCopy=false;
const context={window:{toast:s=>toasts.push(s)},document:{createElement:t=>new Element(t),createTextNode:t=>{const e=new Element('#text');e.textContent=t;return e;}},crypto:{randomUUID:crypto.randomUUID},URL,navigator:{clipboard:{writeText:value=>{writes.push(value);if(rejectCopy)return Promise.reject(Error('denied'));return new Promise(resolve=>pending=resolve);}}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/structured-content.js'),'utf8'),context);
const parser=context.window.StructuredContent,render=s=>{const p=parser.layout(s,0);assert(p,'fixture parses');return parser.layoutRender(p.value,null,p.raw);};
const find=(root,predicate)=>[...(predicate(root)?[root]:[]),...root.children.flatMap(c=>find(c,predicate))];
const roles=(root,role)=>find(root,e=>e.attributes.role===role);
const bars=render('<comparison><bar label="High" value={130} max={100} valueLabel="Original label"/><meter label="Range" min={-10} max={10} value={-5}/><bar label="Missing" value="Unknown"/><bar label="Empty" value=""/></comparison>');
assert.equal(roles(bars,'meter').length,2,'Only measured values get a numeric track');
assert.equal(roles(bars,'meter')[0].children[0].style.width,'100%','Fill is clamped');
assert.equal(roles(bars,'meter')[1].children[0].style.width,'25%','Negative saved scales are honored');
assert(bars.textContent.includes('Original label'));assert(bars.textContent.includes('Unknown'),'Qualitative values remain readable');
const appearance=render('<box border={false} padding={0} height={1} width="95%" background="pink" radius="full"/>').children[0];
assert.equal(appearance.style.height,'4px');assert.equal(appearance.style.width,'95%');assert.equal(appearance.style.border,'0');
const unsafe=render('<box background="url(https://example.com/private)" width="calc(1px)" onclick={alert(1)}><text>Safe text</text></box>').children[0];
assert.equal(unsafe.style.background,undefined);assert.equal(unsafe.style.width,undefined);assert.equal(unsafe.onclick,undefined);
const tabs=render('<tabs selected={1}><tab title="First"><text>First body</text></tab><tab title="Second"><text>Second body</text></tab></tabs>');
const buttons=roles(tabs,'tab'),panels=roles(tabs,'tabpanel');
assert.equal(buttons[1].attributes['aria-selected'],'true');assert.equal(panels[0].hidden,true);
buttons[1].onkeydown({key:'ArrowRight',preventDefault(){}});assert.equal(buttons[0].attributes['aria-selected'],'true');assert.equal(buttons[0].focused,true);
buttons[0].onkeydown({key:'End',preventDefault(){}});assert.equal(buttons[1].attributes['aria-selected'],'true');
buttons[0].onclick();assert.equal(panels[0].hidden,false);
assert.equal(roles(render('<tabs/>'),'tab').length,0,'Empty tabs do not throw');
const unknown=render('<box><future-panel><text>Keep the content</text></future-panel><button onclick={alert(1)}>Remote action</button></box>');
assert(unknown.textContent.includes('Keep the content'));assert.equal(find(unknown,e=>e.tagName==='button')[0].disabled,true);
const details=render('<accordion title="Notes" open><text>Remember this</text></accordion>').children[0];
assert.equal(details.open,true);assert(details.textContent.includes('Remember this'));
const newspaper=render('<newspaper columns={2}><article><heading>One</heading><text>[OK] Arbitrary ✓ text</text></article><column><status color="green" label="[OK]"/><status state="warning">[WARN]</status></column></newspaper>');
assert.equal(newspaper.children[0].style['--rich-dil-columns'],'2');assert(newspaper.textContent.includes('Arbitrary ✓ text'));assert.equal(find(newspaper,e=>e.className==='rich-dil-status rich-dil-status-ok').length,2);
const tableSpec={columns:[{key:'name',label:'Name'},{key:'value',label:'Value'},{key:'status',label:'Status'}],rows:[{name:'Beta',value:20,status:'[WARN]'},{name:'Alpha',value:3,status:'[OK]'}]};
const dataTable=render('<Table content={'+JSON.stringify(tableSpec)+'}/>'),tableBody=find(dataTable,e=>e.tagName==='tbody')[0],sortButtons=find(dataTable,e=>e.className==='rich-dil-sort'),filter=find(dataTable,e=>e.tagName==='input')[0];
assert(tableBody.textContent.includes('Beta20[WARN]'),'JSON table values render');sortButtons[1].onclick();assert.equal(tableBody.children[0].textContent,'Alpha3[OK]','Numeric sorting uses saved values');sortButtons[1].onclick();assert.equal(tableBody.children[0].textContent,'Beta20[WARN]');
filter.value='alpha';filter.oninput();assert.equal(tableBody.children.length,1);filter.value='nothing';filter.oninput();assert.equal(tableBody.children.length,0);filter.value='';filter.oninput();assert.equal(tableBody.children.length,2);
const richTable=render('<table><table-row header><table-cell>Name</table-cell><table-cell>State</table-cell></table-row><table-row><table-cell>[Example](https://example.com)</table-cell><table-cell><status state="ok" label="[OK]"/></table-cell></table-row></table>');
assert(richTable.textContent.includes('Example'));assert(richTable.textContent.includes('[OK]'));
const paged=render('<data-table content={'+JSON.stringify({columns:['value'],rows:Array.from({length:205},(_,i)=>({value:i}))})+'}/>'),pagedBody=find(paged,e=>e.tagName==='tbody')[0],next=find(paged,e=>e.tagName==='button'&&e.textContent==='Next')[0];
assert.equal(pagedBody.children.length,100);next.onclick();assert.equal(pagedBody.children[0].textContent,'100');next.onclick();assert.equal(pagedBody.children.length,5);
(async()=>{
 const block=render('<copy label="Example" text={'+JSON.stringify('line one\nline two')+'}/>'),button=find(block,e=>e.tagName==='button')[0];
 const first=button.onclick();await button.onclick();assert.equal(writes.length,1,'Repeated activation has one pending clipboard write');pending();await first;
 assert.equal(writes[0],'line one\nline two');assert.equal(button.dataset.busy,undefined);assert.equal(toasts.at(-1),'Copied');
 rejectCopy=true;await button.onclick();assert.match(toasts.at(-1),/Copy unavailable/,'Failure is visible instead of a false success');
 rejectCopy=false;filter.value='alpha';filter.oninput();const tableCopy=find(dataTable,e=>e.tagName==='button'&&e.textContent==='Copy')[0],copying=tableCopy.onclick();pending();await copying;assert.equal(writes.at(-1),'Name\tValue\tStatus\nAlpha\t3\t[OK]','Table copy retains labels and all matching data');
 console.log('Dynamic controls: saved ranges, qualitative labels, layout attributes, safe fallbacks, tabs/keyboard, disclosures, copy and repeated activation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
