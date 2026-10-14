'use strict';
window.TablePreferences=(()=>{
 const MODES=['clean','fit','wide','compact','sleek','expanded'];
 let mode='clean',openOverride=null,conversation=null,menu=null,trigger=null;
 const $=id=>document.getElementById(id);
 function preference(){return MODES.includes(S?.settings?.tableLayout)?S.settings.tableLayout:'clean';}
 function setMode(value,persist=true){
  if(!MODES.includes(value))return;
  mode=value;
  const main=$('main');
  if(main){for(const item of MODES)main.classList.toggle('table-global-'+item,item===mode);}
  if(menu)for(const button of menu.querySelectorAll('[data-table-mode]')){const pressed=button.dataset.tableMode===mode;button.setAttribute('aria-checked',String(pressed));}
  if(trigger){trigger.title='All table layouts · '+mode;trigger.setAttribute('aria-label','All table layouts: '+mode);}
  for(const card of document.querySelectorAll('#messages .table-card'))applyCard(card);
  if(persist){S.settings.tableLayout=mode;saveSetting('tableLayout',mode).catch(error=>toast(error.message));}
 }
 function applyCard(card){
  card.dataset.globalTableMode=mode;
  const table=card.querySelector('table');if(!table)return;
  table.classList.toggle('fit-table',mode==='fit'||mode==='expanded');
  table.classList.toggle('compact-table',mode==='compact');
  const fit=card.querySelector('.table-fit'),compact=card.querySelector('.table-compact');
  if(fit){const fitted=table.classList.contains('fit-table');fit.textContent=fitted?'Wide':'Fit';fit.title=fitted?'Use wide columns with horizontal scrolling':'Fit columns to reading width';fit.setAttribute('aria-pressed',String(fitted));}
  if(compact)compact.setAttribute('aria-pressed',String(table.classList.contains('compact-table')));
  const viewport=card.querySelector('.table-wrap'),toggle=card.querySelector('.table-toggle');
  if(viewport&&openOverride!==null){
   viewport.hidden=!openOverride;
   if(toggle){toggle.textContent=openOverride?'▾':'▸';toggle.setAttribute('aria-expanded',String(openOverride));toggle.setAttribute('aria-label',openOverride?'Collapse table':'Expand table');}
  }
 }
 function forConversation(cid){
  if(cid!==conversation){conversation=cid;openOverride=null;}
 }
 function setAll(open){
  openOverride=open;
  for(const card of document.querySelectorAll('#messages .table-card'))applyCard(card);
 }
 function setMenu(open){
  if(!menu)return;
  menu.hidden=!open;
  trigger?.setAttribute('aria-expanded',String(open));
  if(open){const rect=trigger.getBoundingClientRect();menu.style.right=Math.max(8,innerWidth-rect.right)+'px';menu.style.top=Math.min(innerHeight-menu.offsetHeight-12,rect.bottom+7)+'px';}
 }
 function bind(){
  const header=document.querySelector('.header-right');
  if(!header)return;
  trigger=document.createElement('button');trigger.id='table-layout-open';trigger.type='button';trigger.className='icon';trigger.title='All table layouts';trigger.setAttribute('aria-label','All table layouts');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls','table-layout-menu');
  trigger.append(ViewerIcons.svg('sliders'));
  header.insertBefore(trigger,$('chat-menu'));
  menu=document.createElement('section');menu.id='table-layout-menu';menu.hidden=true;menu.setAttribute('aria-label','All tables in this conversation');
  const heading=document.createElement('div');heading.className='table-menu-heading';heading.textContent='All tables';
  const list=document.createElement('div');list.className='table-menu-styles';list.setAttribute('role','radiogroup');list.setAttribute('aria-label','Table layout');
  for(const [name,label,description] of [
   ['clean','Clean','Like ChatGPT · simple lines'],
   ['fit','Fit','Fit all columns to width'],
   ['wide','Wide','Keep wide columns, scroll'],
   ['compact','Compact','Tighter rows and text'],
   ['sleek','Sleek','Minimal toolbar and separators'],
   ['expanded','Expanded','Use full conversation width']
  ]){
   const b=document.createElement('button');b.type='button';b.dataset.tableMode=name;b.setAttribute('role','radio');b.setAttribute('aria-checked','false');b.textContent=label;
   const small=document.createElement('small');small.textContent=description;b.append(small);
   b.onclick=()=>{setMode(name);setMenu(false);};list.append(b);
  }
  const actions=document.createElement('div');actions.className='table-menu-actions';
  for(const [name,open] of [['Expand every table',true],['Collapse every table',false]]){
   const b=document.createElement('button');b.type='button';b.textContent=name;b.onclick=()=>{setAll(open);setMenu(false);};actions.append(b);
  }
  menu.append(heading,list,actions);document.body.append(menu);
  trigger.onclick=()=>setMenu(menu.hidden);
  document.addEventListener('pointerdown',e=>{if(!menu.hidden&&!menu.contains(e.target)&&!trigger.contains(e.target))setMenu(false);});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!menu.hidden){e.preventDefault();e.stopImmediatePropagation();setMenu(false);trigger.focus({preventScroll:true});}},true);
  window.addEventListener('resize',()=>{if(!menu.hidden)setMenu(true);});
  setMode(preference(),false);
 }
 document.addEventListener('DOMContentLoaded',bind);
 return {applyCard,setMode,setAll,forConversation,getMode:()=>mode};
})();
