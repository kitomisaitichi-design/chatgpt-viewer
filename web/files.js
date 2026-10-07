'use strict';
window.ArchiveFiles=(()=>{
 let generation=0,offset=0,conversation='',data=null;
 const get=id=>document.getElementById(id),run=f=>(...a)=>Promise.resolve().then(()=>f(...a)).catch(e=>toast(e.message));
 const sizeText=n=>n==null?'Unknown size':n<1000?n+' bytes':n<1000000?(n/1000).toFixed(1)+' KB':(n/1000000).toFixed(2)+' MB';
 async function load(reset=true){
  const g=++generation;if(reset){offset=0;get('files-list').replaceChildren();}
  get('files-summary').textContent='Reading your saved file catalog…';
  const result=await api('/api/files?'+new URLSearchParams({search:get('files-search').value,status:get('files-status').value,source:get('files-source').value,conversation,offset,limit:50}));if(g!==generation)return;
  data=result;get('files-summary').textContent=result.counts.saved+' available locally · '+result.counts.manual+' manual · '+result.total+' matching files'+(conversation?' · selected chat':'');
  const fragment=document.createDocumentFragment();
  for(const f of result.entries){
   const row=el('article','saved-file'),description=el('div','saved-file-description'),name=el('strong','',f.name),meta=el('small','',sizeText(f.size)+' · '+f.status+' · '+(f.sources?.join(' + ')||f.source));description.append(name,meta);if(f.historical)description.append(el('small','','Previous saved version · original bytes retained'));else if(f.retained)description.append(el('small','','A source reference is absent or unavailable; saved copies are retained'));if(f.duplicate_of)description.append(el('small','','Shared content · '+f.duplicate_of));if(f.source_refs?.length){const details=el('details'),summary=el('summary','','Source names & history');details.append(summary);for(const ref of f.source_refs)details.append(el('small','',(ref.kind||'Source')+' · '+(ref.name||f.name)+' · '+(ref.presence||'Observed reference')));description.append(details);}if(f.error)description.append(el('small','',f.error));if(f.path)description.append(el('code','',f.path));
   const controls=el('div','saved-file-actions');
   if(f.available){const a=el('a','secondary',f.image?'Open image':'Download saved file');a.href='/api/files/content?'+new URLSearchParams({key:f.key,inline:f.image?'1':'0'});a.target='_blank';a.rel='noopener noreferrer';if(f.image&&f.conversations.length){a.onclick=e=>{e.preventDefault();get('files-dialog').close();ThreadImages.open(conversation||f.conversations[0],f.key,a,conversation===S.selected?.id?S.leaf:null).catch(error=>toast(error.message));};}controls.append(a);}
   else{const a=el('a','secondary','Find in ChatGPT ↗');a.href=f.manual_url;a.target='_blank';a.rel='noopener noreferrer';controls.append(a);if(f.path){const button=el('button','','Import downloaded copy');button.onclick=run(async()=>{const chosen=await api('/api/files/pick',{});if(!chosen.path)return;await api('/api/files/import',{key:f.key,path:chosen.path});toast('Downloaded file copied into this backup.');await load();});controls.append(button);}}
   if(f.conversations.length){const button=el('button','','Source chat');button.onclick=run(async()=>{get('files-dialog').close();await openChat(f.conversations[0]);});controls.append(button);}
   row.append(description,controls);fragment.append(row);
  }
  get('files-list').append(fragment);offset+=result.entries.length;get('files-more').hidden=!result.has_more;
  if(!offset)get('files-list').append(el('p','muted','No files match. Use exporter Library backup to populate its catalog, or choose a different filter.'));
  get('files-notes').textContent=result.notes.join('\n');
 }
 function open(id=''){conversation=id;get('files-chat-only').checked=!!id;get('files-dialog').showModal();void run(()=>load())();}
 function init(){get('files-open').onclick=()=>open();get('chat-files-open').onclick=()=>window.ExportInterop?ExportInterop.openFiles():open(S.selected?.id || '');let timer;get('files-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>void run(()=>load())(),180);};get('files-status').onchange=run(()=>load());get('files-source').onchange=run(()=>load());get('files-chat-only').onchange=run(()=>{conversation=get('files-chat-only').checked?S.selected?.id || '':'';return load();});get('files-refresh').onclick=run(()=>load());get('files-more').onclick=run(()=>load(false));}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
 return {open,refresh:()=>load()};
})();
