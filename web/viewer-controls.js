'use strict';
window.ViewerControls=(()=>{
 const icon=(b,n,label='')=>ViewerIcons.set(b,n,label);
 async function theme(value){const previous=S.settings.theme||'dark';if(value==='light'&&previous!=='light')await saveSetting('lastDarkTheme',previous);await saveSetting('theme',value);if(value!=='light')await saveSetting('lastDarkTheme',value);applyAppearance();}
 function init(){const bar=document.querySelector('.header-right');for(const [id,n] of [['chat-files-open','file'],['chat-images-open','image'],['inchat-open','search'],['pin-chat','star'],['chat-menu','more']]){const b=document.getElementById(id);if(b)icon(b,n);}
  const bulb=el('button','icon'),palette=el('button','icon'),copy=el('button','thread-copy');bulb.id='brightness-toggle';bulb.title='Toggle light / dark';bulb.setAttribute('aria-label',bulb.title);icon(bulb,'bulb');bulb.onclick=safeRun(()=>theme(S.settings.theme==='light'?(S.settings.lastDarkTheme||'dark'):'light'));
  palette.id='theme-picker-open';palette.title='Choose theme';palette.setAttribute('aria-label',palette.title);palette.setAttribute('aria-haspopup','dialog');icon(palette,'palette');
  const pop=el('dialog','theme-picker');pop.setAttribute('aria-label','Choose theme');pop.append(el('h3','','Theme'));
  const list=el('div','theme-list');list.setAttribute('role','group');list.setAttribute('aria-label','Theme choices');pop.append(list);
  const select=document.getElementById('theme');select.replaceChildren();
  for(const t of [...VIEWER_THEMES].sort((a,b)=>a.label.localeCompare(b.label,'en'))){
   const option=el('option','',t.label);option.value=t.id;select.append(option);
   const b=el('button','theme-choice');b.dataset.theme=t.id;
   const swatch=el('span','theme-swatch'+(t.id==='custom'?' theme-swatch-custom':''));swatch.setAttribute('aria-hidden','true');
   if(t.colors)swatch.style.background=`linear-gradient(135deg,${t.colors[5]},${t.colors[0]} 75%)`;
   const label=el('span','theme-label',t.label),mark=el('span','theme-mark');mark.setAttribute('aria-hidden','true');icon(mark,'check');b.append(swatch,label,mark);
   b.onclick=safeRun(async()=>{await theme(t.id);pop.close();palette.focus();if(t.id==='custom')openSettings();});list.append(b);
  }
  const close=el('button','theme-close');icon(close,'close','Close');close.onclick=()=>{pop.close();palette.focus();};pop.append(close);document.body.append(pop);
  palette.onclick=()=>{list.querySelectorAll('[data-theme]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.theme===(S.settings.theme||'dark'))));pop.showModal();list.scrollTop=0;const active=list.querySelector('[aria-pressed=true]');active?.focus({preventScroll:true});};
  pop.addEventListener('click',event=>{if(event.target===pop){const r=pop.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)pop.close();}});
  copy.id='copy-thread';copy.title='Copy complete thread Markdown';icon(copy,'copy','Copy text');copy.onclick=safeRun(async()=>{if(!S.selected){toast('Open a conversation first.');return;}copy.disabled=true;const cid=S.selected.id,leaf=S.leaf,controller=new AbortController(),timer=setTimeout(()=>controller.abort(),60000);try{const r=await fetch('/api/thread-markdown?'+new URLSearchParams({id:cid,...(leaf?{leaf}:{})}),{signal:controller.signal});if(!r.ok){const e=await r.json();throw Error(e.error||'Markdown unavailable');}const text=await r.text();await navigator.clipboard.writeText(text);toast(r.headers.get('X-Markdown-Source')==='original'?'Original Markdown copied':'Markdown copied · generated from saved branch; no matching Markdown original');}finally{clearTimeout(timer);copy.disabled=false;}});bar.prepend(bulb,palette,copy);
 }
 document.addEventListener('DOMContentLoaded',init);return {theme};
})();
