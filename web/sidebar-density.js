'use strict';
window.SidebarDensity=(()=>{
 let panel=null,scaleInput=null,scaleValue=null,scaleButton=null,moreButton=null,view=null;
 const clamp=value=>Math.max(70,Math.min(115,Math.round((Number(value)||85)/5)*5));
 const auto=()=>innerHeight<=720?70:innerHeight<=900?75:innerHeight<=1100?85:90;
 function apply(value){
  const automatic=value==='auto'||value===undefined||value===null;
  const size=automatic?auto():clamp(value);
  document.getElementById('sidebar')?.style.setProperty('--sidebar-ui-scale',String(size/100));
  if(scaleInput)scaleInput.value=String(size);
  if(scaleValue)scaleValue.textContent=(automatic?'Auto · ':'')+size+'%';
  if(scaleButton)scaleButton.title='Sidebar UI size · '+(automatic?'Auto · ':'')+size+'%';
  return size;
 }
 const make=(id,name,label,fn)=>{
  const b=document.createElement('button');b.id=id;b.type='button';b.className='sidebar-dock-button';b.setAttribute('aria-label',label);b.title=label;b.append(ViewerIcons.svg(name));b.onclick=fn;return b;
 };
 function toggle(which){
  if(!panel)return;
  const open=panel.hidden||view!==which;
  view=open?which:null;panel.hidden=!open;
  panel.querySelector('#sidebar-size-controls').hidden=view!=='scale';
  panel.querySelector('#sidebar-more-controls').hidden=view!=='more';
  scaleButton.setAttribute('aria-expanded',String(view==='scale'));moreButton.setAttribute('aria-expanded',String(view==='more'));
 }
 function bind(){
  const sidebar=document.getElementById('sidebar'),bottom=sidebar?.querySelector('.sidebar-bottom');
  const bookmarks=document.getElementById('bookmarks-open'),trash=document.getElementById('trash-open'),settings=document.getElementById('settings-open');
  if(!sidebar||!bottom||!bookmarks||!trash||!settings)return;
  panel=document.createElement('section');panel.id='sidebar-utility-panel';panel.hidden=true;panel.setAttribute('aria-label','Sidebar controls');
  const scale=document.createElement('div');scale.id='sidebar-size-controls';
  const heading=document.createElement('div');heading.className='sidebar-utility-title';heading.textContent='Sidebar size';
  scaleValue=document.createElement('output');scaleValue.id='sidebar-scale-value';heading.append(scaleValue);
  scaleInput=document.createElement('input');scaleInput.id='sidebar-scale';scaleInput.type='range';scaleInput.min='70';scaleInput.max='115';scaleInput.step='5';
  scaleInput.setAttribute('aria-label','Sidebar UI size, percent');
  scaleInput.oninput=()=>apply(scaleInput.value);
  scaleInput.onchange=()=>saveSetting('sidebarUIScale',apply(scaleInput.value)).catch(error=>toast(error.message));
  const presets=document.createElement('div');presets.className='sidebar-size-presets';
  for(const [percent,label] of [['auto','Auto'],[70,'Small'],[85,'Compact'],[100,'Normal']]){
   const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=()=>{apply(percent);void saveSetting('sidebarUIScale',percent).catch(error=>toast(error.message));};presets.append(b);
  }
  scale.append(heading,scaleInput,presets);
  const more=document.createElement('div');more.id='sidebar-more-controls';
  const footer=sidebar.querySelector('.catalog-footer'),status=document.getElementById('status'),scan=document.getElementById('scan-toggle'),profile=bottom.querySelector('.profile'),queue=document.getElementById('delete-queue-open');
  for(const item of [footer,status,scan,queue,profile])if(item)more.append(item);
  panel.append(scale,more);
  const dock=document.createElement('div');dock.id='sidebar-icon-dock';
  function iconify(node,name,label){
   const badge=node.querySelector('small');node.replaceChildren(ViewerIcons.svg(name));if(badge)node.append(badge);
   node.className='sidebar-dock-button';node.title=label;node.setAttribute('aria-label',label);
   return node;
  }
  dock.append(iconify(bookmarks,'bookmark','Bookmarks'),iconify(trash,'trash','Trash'));
  scaleButton=make('sidebar-size-open','sliders','Adjust sidebar UI size',()=>toggle('scale'));
  scaleButton.setAttribute('aria-expanded','false');scaleButton.setAttribute('aria-controls','sidebar-utility-panel');
  moreButton=make('sidebar-more-open','more','More sidebar controls, status and rescan',()=>toggle('more'));
  moreButton.setAttribute('aria-expanded','false');moreButton.setAttribute('aria-controls','sidebar-utility-panel');
  dock.append(scaleButton,iconify(settings,'palette','Settings & appearance'),moreButton);
  dock.addEventListener('click',e=>{if(!panel.hidden&&e.target.closest('#bookmarks-open,#trash-open,#settings-open'))toggle(view);});
  bottom.replaceChildren(panel,dock);
  document.addEventListener('pointerdown',e=>{
   if(!panel.hidden&&!bottom.contains(e.target))toggle(view);
  });
  document.addEventListener('keydown',e=>{
   if(e.key==='Escape'&&!panel.hidden){e.preventDefault();e.stopImmediatePropagation();toggle(view);}
  },true);
  apply(S.settings?.sidebarUIScale??'auto');
  window.addEventListener('resize',()=>{if(!S.settings?.sidebarUIScale||S.settings.sidebarUIScale==='auto')apply('auto');});
  const observer=new MutationObserver(()=>{
   if(status)moreButton.title='More sidebar controls · '+status.textContent;
  });
  if(status)observer.observe(status,{childList:true,characterData:true,subtree:true});
 }
 document.addEventListener('DOMContentLoaded',bind);
 return {apply,clamp};
})();
