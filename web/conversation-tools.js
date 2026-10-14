'use strict';
window.ConversationTools=(()=>{
 let selected=new Set(),anchor=null,selecting=false,staging=false,bar=null,panel=null,toggle=null,dragOrigin=null,position=null;
 const visible=()=>[...$('chat-list').querySelectorAll('.chat-row')].map(n=>n.dataset.id);
 const matching=()=>CatalogControls.filter(S.chats,true).filter(c=>S.type==='all'||kind(c)===S.type);
 const agents=()=>matching().filter(CatalogModel.isSubagent);
 function button(id,label,fn){const b=el('button','',label);b.id=id;b.type='button';b.onclick=safeRun(fn);return b;}
 function paint(row){const chosen=selected.has(row.dataset.id);row.classList.toggle('bulk-selected',chosen);row.children[0]?.setAttribute('aria-pressed',String(chosen));}
 function positionPanel(reset=false){
  if(!panel||panel.hidden)return;
  const width=panel.offsetWidth,height=panel.offsetHeight,margin=12;
  const reference=toggle.getBoundingClientRect();
  const initial={x:Math.min(reference.left,window.innerWidth-width-margin),y:reference.bottom+8};
  const next=reset||!position?initial:position;
  position={x:Math.max(margin,Math.min(next.x,Math.max(margin,window.innerWidth-width-margin))),y:Math.max(margin,Math.min(next.y,Math.max(margin,window.innerHeight-height-margin)))};
  panel.style.left=position.x+'px';panel.style.top=position.y+'px';
 }
 function setOpen(open,focus=false){
  if(!panel)return;
  panel.hidden=!open;toggle.setAttribute('aria-expanded',String(open));
  if(open){position=null;positionPanel(true);if(focus)panel.focus({preventScroll:true});}
  else if(focus)toggle.focus({preventScroll:true});
 }
 function update(){
  if(!bar)return;const ids=visible(),visibleSet=new Set(ids),hidden=[...selected].filter(id=>!visibleSet.has(id)).length;
  $('selection-count').textContent=selected.size+' selected'+(hidden?' · '+hidden+' hidden':'');
  $('selection-start').setAttribute('aria-label',selecting?'Finish selecting chats':'Select multiple chats');$('selection-start').title=$('selection-start').getAttribute('aria-label');$('selection-start').setAttribute('aria-pressed',String(selecting));
  $('selection-inline-count').textContent=selected.size?selected.size+' selected':'';
  toggle.setAttribute('aria-label',(selected.size?selected.size+' selected · ':'')+'Selection tools');toggle.title=toggle.getAttribute('aria-label');
  bar.classList.toggle('has-selection',!!selected.size);
  for(const id of ['selection-all','selection-invert'])$(id).disabled=!ids.length||S.sidebarRendering;
  $('selection-backup').disabled=!selected.size; $('selection-clear').disabled=!selected.size;$('selection-delete').disabled=!selected.size||staging;
  const list=agents();$('selection-subagents').textContent='Select subagents ('+list.length+')';$('selection-subagents').disabled=!list.length||staging;
  for(const row of $('chat-list').querySelectorAll('.chat-row'))paint(row);
 }
 function sync(){
  if(!bar)return;const allowed=new Set(matching().map(c=>c.id));selected=new Set([...selected].filter(id=>allowed.has(id)));
  if(!allowed.has(anchor))anchor=null;$('hide-subagents').checked=S.settings.hideSubagents!==false;update();
 }
 function row(node,c){paint(node);node.classList.toggle('subagent-row',CatalogModel.isSubagent(c));if(CatalogModel.isSubagent(c))node.children[0].title+='\nCodex subagent'+(c.agent_nickname?' · '+c.agent_nickname:'');}
 async function openFolder(id,target='workspace',reference=''){
  const result=await api('/api/conversation/open-folder',{id,target,reference});toast('Opened folder · '+result.path);return result;
 }
 async function decorateFolder(node,reference){
  const c=S.selected,leaf=S.leaf;if(!c||!reference)return;
  try{const data=await ThreadAttachments.catalog(c.id,leaf),item=data.attachments.find(a=>a.kind==='folder'&&a.references.includes(reference));
   if(!item||!node.isConnected||S.selected?.id!==c.id||S.leaf!==leaf)return;
   node.href='#';node.classList.add('native-file-link');node.title='Open local folder · '+item.folder_path;node.dataset.folderLink=reference;
   node.onclick=e=>{e.preventDefault();safeRun(()=>openFolder(c.id,'reference',reference))();};
  }catch(error){if(node.isConnected)node.title='Folder lookup failed: '+error.message;}
 }
 function header(){
  const c=S.selected;for(const [id,target] of [['conversation-home','workspace'],['conversation-source','source']]){const b=$(id);if(!b)continue;b.hidden=!c||target==='workspace'&&!c.workspace;b.title=target==='workspace'?c?.workspace||'No recorded home folder':c?.path||'';}
 }
 async function stage(){if(staging||!selected.size)return;staging=true;update();try{await Collections.stage([...selected]);}finally{staging=false;update();}}
 function bind(){
  bar=el('section','conversation-selection');bar.setAttribute('aria-label','Conversation selection');
  const main=el('div','selection-inline');
  main.append(button('selection-start','',()=>{selecting=!selecting;update();}),el('span','selection-inline-count'),button('selection-toggle','',()=>setOpen(panel.hidden,true)));
  ViewerIcons.set(main.firstChild,'check');ViewerIcons.set(main.lastChild,'sliders');
  main.firstChild.setAttribute('aria-label','Select multiple chats');main.firstChild.title='Select multiple chats';
  main.children[1].id='selection-inline-count';main.children[1].setAttribute('role','status');
  toggle=main.lastChild;toggle.setAttribute('aria-controls','selection-actions');toggle.setAttribute('aria-expanded','false');toggle.title='Selection tools';
  bar.append(main);$('chat-list').before(bar);
  panel=el('section','selection-actions selection-panel');panel.id='selection-actions';panel.hidden=true;panel.tabIndex=-1;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Conversation selection tools');
  const handle=el('div','selection-panel-head');handle.id='selection-panel-handle';handle.title='Drag to move this panel';
  const heading=el('div','selection-panel-heading'),caption=el('strong','','Selection tools'),count=el('span','','0 selected');count.id='selection-count';count.setAttribute('role','status');heading.append(caption,count);
  const close=button('selection-panel-close','×',()=>setOpen(false,true));close.setAttribute('aria-label','Close selection tools');close.title='Close panel';handle.append(heading,close);panel.append(handle);
  const heading1=el('div','selection-panel-label','Choose conversations'),scope=el('div','selection-scope');
  const hide=el('label','selection-hide'),check=el('input');check.id='hide-subagents';check.type='checkbox';check.checked=S.settings.hideSubagents!==false;hide.append(check,document.createTextNode('Hide subagents'));
  check.onchange=safeRun(async()=>{const saving=saveSetting('hideSubagents',check.checked);renderSidebar();await saving;});
  scope.append(button('selection-all','All visible',()=>{selected=new Set(visible());anchor=null;update();}),button('selection-invert','Invert visible',()=>{selected=ConversationSelectionModel.invert(selected,visible());anchor=null;update();}),button('selection-clear','Clear',()=>{selected.clear();anchor=null;update();}));
  const agentControls=el('div','selection-agent-controls');agentControls.append(button('selection-subagents','Select subagents',()=>{selected=new Set(agents().map(c=>c.id));anchor=null;selecting=true;update();}),hide);
  const actionLabel=el('div','selection-panel-label','Selected conversations'),actions=el('div','selection-primary-actions');
  actions.append(button('selection-backup','Back up selected…',()=>SelectedBackup.open([...selected])),button('selection-delete','Queue deletion…',stage));
  const hint=el('small','selection-hint','Ctrl-click toggles · Shift-click selects a range · drag the heading to move this panel');
  panel.append(heading1,scope,agentControls,actionLabel,actions,hint);document.body.append(panel);
  handle.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('button'))return;dragOrigin={pointer:e.pointerId,x:e.clientX,y:e.clientY,left:panel.offsetLeft,top:panel.offsetTop};handle.setPointerCapture(e.pointerId);e.preventDefault();});
  handle.addEventListener('pointermove',e=>{if(!dragOrigin||e.pointerId!==dragOrigin.pointer)return;position={x:dragOrigin.left+e.clientX-dragOrigin.x,y:dragOrigin.top+e.clientY-dragOrigin.y};positionPanel();});
  for(const event of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(event,()=>{dragOrigin=null;});
  window.addEventListener('resize',()=>positionPanel());
  document.addEventListener('pointerdown',e=>{if(!panel.hidden&&!panel.contains(e.target)&&!toggle.contains(e.target))setOpen(false);});
  $('chat-list').addEventListener('click',e=>{const b=e.target.closest('.chat-row > button:first-child');if(!b)return;const row=b.closest('.chat-row'),modified=e.ctrlKey||e.metaKey||e.shiftKey||selecting;
   if(modified){e.preventDefault();e.stopImmediatePropagation();if(S.sidebarRendering)return;const result=ConversationSelectionModel.click(selected,anchor,visible(),row.dataset.id,{ctrl:e.ctrlKey||e.metaKey,shift:e.shiftKey,toggle:selecting});selected=result.selected;anchor=result.anchor;update();}
   else{selected.clear();anchor=row.dataset.id;update();}
  },true);
  $('chat-list').addEventListener('mousedown',e=>{if(e.shiftKey&&e.target.closest('.chat-row'))e.preventDefault();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.querySelector('dialog[open]')){if(!panel.hidden){setOpen(false,true);e.preventDefault();e.stopImmediatePropagation();return;}if(!e.target.closest('input,textarea,select,[contenteditable="true"]')){selected.clear();selecting=false;anchor=null;update();}}});
  const folders=el('span','conversation-folder-actions');folders.append(button('conversation-home','Home folder',()=>S.selected&&openFolder(S.selected.id)),button('conversation-source','Source folder',()=>S.selected&&openFolder(S.selected.id,'source')));$('catalog-chat-bar').append(folders);header();sync();
 }
 document.addEventListener('DOMContentLoaded',bind);
 return {sync,row,header,update,openFolder,decorateFolder};
})();
