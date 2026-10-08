'use strict';
window.AttachmentFinder=(()=>{
 function create(controls,adapter){
  const make=(tag,cls='',text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
  const panel=make('section','attachment-find-panel');panel.hidden=true;panel.setAttribute('aria-label','Find in document');
  const input=make('input');input.type='search';input.placeholder='Find in document';input.maxLength=500;input.setAttribute('aria-label','Find in attachment');
  const field=make('div','attachment-find-field');field.append(ViewerIcons.svg('search'),input);
  const find=make('button','attachment-find-submit','Find');find.title='Next match · Enter';find.setAttribute('aria-expanded','false');find.setAttribute('aria-controls','attachment-find-panel');panel.id='attachment-find-panel';controls.append(field,find);
  const head=make('div','attachment-find-heading'),label=make('div'),heading=make('strong','','Find'),hint=make('small','','Enter to continue · Shift+Enter to go back');label.append(heading,hint);
  const nav=make('div','attachment-find-navigation'),count=make('span','attachment-find-count','0 of 0');count.setAttribute('role','status');count.setAttribute('aria-live','polite');
  const icon=(name,glyph,action)=>{const b=make('button');b.title=name;b.setAttribute('aria-label',name);b.append(ViewerIcons.svg(glyph));b.onclick=action;return b;};
  const back=icon('Previous match · Shift+Enter','left',()=>run(-1)),next=icon('Next match · Enter','right',()=>run(1)),dismiss=icon('Close document find','close',close);nav.append(back,count,next);head.append(label,nav,dismiss);
  const optionRow=make('div','attachment-find-options'),options={caseSensitive:false,wholeWord:false,regex:false,highlightAll:true},switches=[];
  for(const [key,text] of [['caseSensitive','Case sensitive'],['wholeWord','Whole word'],['regex','Regex'],['highlightAll','Highlight all']]){
   const b=make('button','attachment-find-option');b.setAttribute('role','switch');b.setAttribute('aria-label',text);b.title=key==='regex'?'Use a regular expression (maximum 500 characters)':text;b.append(make('span','attachment-find-switch'),make('span','',text));
   b.onclick=()=>{options[key]=!options[key];syncOptions();if(key==='highlightAll')paint(false).catch(e=>status.textContent=e.message);else{invalidate();if(input.value)run(1);}};switches.push([key,b]);optionRow.append(b);
  }
  const status=make('p','attachment-find-status','Enter text to find.');status.setAttribute('role','status');panel.append(head,optionRow,status);
  let generation=0,source=null,hits=[],index=-1,key='',worker=null,cancelWorker=null,busy=false,limited=false;
  function syncOptions(){for(const [key,b] of switches)b.setAttribute('aria-checked',String(options[key]));}
  function sync(){back.disabled=next.disabled=busy||!hits.length;find.disabled=busy;panel.setAttribute('aria-busy',String(busy));count.textContent=busy?'Finding…':`${index<0?0:index+1} of ${hits.length}${limited?'+':''}`;}
  function open(){panel.hidden=false;find.setAttribute('aria-expanded','true');}
  function invalidate(){generation++;cancelWorker?.();cancelWorker=null;worker?.terminate();worker=null;busy=false;hits=[];index=-1;key='';limited=false;adapter.clear();status.textContent=input.value?'Press Find or Enter to search.':'Enter text to find.';sync();}
  function reset(closePanel=true){invalidate();source=null;if(closePanel){panel.hidden=true;find.setAttribute('aria-expanded','false');input.value='';Object.assign(options,{caseSensitive:false,wholeWord:false,regex:false,highlightAll:true});syncOptions();}}
  function close(){reset();input.focus({preventScroll:true});}
  async function paint(reveal=true){if(panel.hidden||index<0)return;const request=generation,selected=hits[index],local=hits.filter(h=>h.segment===selected.segment);await adapter.reveal(source.segments[selected.segment],selected,local,local.indexOf(selected),options.highlightAll,reveal,{hits,segments:source.segments,index,current:()=>request===generation&&!panel.hidden});}
  function match(segments,query,current){return new Promise((resolve,reject)=>{
   const w=worker=new Worker('document-search-worker.js');let timer;
   const finish=(error,result)=>{clearTimeout(timer);w.terminate();if(worker===w){worker=null;cancelWorker=null;}error?reject(error):resolve(result);};cancelWorker=()=>finish(Error('Search cancelled'));
   timer=setTimeout(()=>finish(Error('Search took too long. Try a simpler pattern or fewer characters.')),2500);
   w.onmessage=e=>finish(e.data.error?Error(e.data.error):null,e.data);w.onerror=e=>finish(Error(e.message||'Document search failed. Try again.'));w.postMessage({segments:segments.map(s=>({text:s.text})),query,options});
  });}
  async function run(direction=1){
   open();if(busy)return;if(!input.value){invalidate();return;}
   const nextKey=JSON.stringify([input.value,options.caseSensitive,options.wholeWord,options.regex]);
   const request=generation,current=()=>request===generation&&!panel.hidden;
   try{
    if(key!==nextKey){busy=true;status.textContent='Searching the document…';sync();const loaded=source||await adapter.source(current,message=>{if(current())status.textContent=message;});if(!current())return;source=loaded;const result=await match(source.segments,input.value,current);if(!current())return;hits=result.hits;limited=result.limited;index=-1;key=nextKey;}
    if(!hits.length){adapter.clear();status.textContent='No matches. Try another word or turn off a search option.';return;}
    index=index<0?(direction<0?hits.length-1:0):(index+direction+hits.length)%hits.length;
    status.textContent=(limited?'Showing the first 10,000 matches. ':'')+(source.note||'Wraps from the last match to the first.');await paint();
   }catch(error){if(current()){adapter.clear();hits=[];index=-1;key='';status.textContent=error.message;}}
   finally{if(current()){busy=false;sync();}}
  }
  find.onclick=()=>run(1);input.oninput=()=>invalidate();input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();run(e.shiftKey?-1:1);}if(e.key==='Escape'&&!panel.hidden){e.preventDefault();e.stopPropagation();close();}};
  panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();}});syncOptions();sync();
  return {panel,reset,invalidate,refresh:()=>paint(false),isOpen:()=>!panel.hidden,search:()=>run(1)};
 }
 return {create};
})();
