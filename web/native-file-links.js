'use strict';
/* Cross-link saved source filenames to the conversation already indexed from them.
 * Never opens an arbitrary file:// URL or a path supplied by chat content. */
window.NativeFileLinks=(()=>{
 const names=/(?:[A-Za-z]:[\\/])?(?:[\w.@+()\-]+[\\/])*[\w.@+()\-]+\.(?:jsonl|json|md)\b/gi;
 const prohibited='a,button,pre,code,kbd,samp,textarea,script,style,.saved-widget,.source-refs';
 let chooser=null;
 function candidates(text){
  if(typeof text!=='string'||text.length>131072||!(/\.(?:jsonl|json|md)\b/i.test(text)))return [];
  return [...text.matchAll(names)].filter(m=>m[0].length<=400&&!(m.index>0&&/[:/]/.test(text.slice(Math.max(0,m.index-3),m.index)))).slice(0,35);
 }
 function decorate(root){
  if(!root)return;
  // Markdown's sanitized relative links already point at /api/asset. Prefer
  // opening their indexed conversation, but preserve the original download
  // when no matching parsed chat exists.
  for(const anchor of root.querySelectorAll('a[href]')){
   if(anchor.dataset.parsedSource)continue;
   let url;try{url=new URL(anchor.getAttribute('href'),location.href);}catch{continue;}
   if(url.origin!==location.origin||url.pathname!=='/api/asset')continue;
   const path=url.searchParams.get('path')||'';
   if(!candidates(path).some(match=>match[0]===path))continue;
   anchor.classList.add('native-file-link');anchor.title='Open parsed source in viewer (or download if not indexed)';
   anchor.dataset.parsedSource=path;
   anchor.addEventListener('click',event=>{
    event.preventDefault();
    void open(path,true).then(found=>{if(!found)window.open(url.href,'_blank','noopener,noreferrer');})
      .catch(error=>window.toast?.(error.message));
   });
  }
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];
  while(walker.nextNode()){const node=walker.currentNode;if(node.parentElement&&!node.parentElement.closest(prohibited)&&candidates(node.textContent).length)nodes.push(node);}
  for(const node of nodes){
   const hits=candidates(node.textContent);if(!hits.length)continue;
   const frag=document.createDocumentFragment();let last=0;
   for(const match of hits){const value=match[0],start=match.index;
    if(start<last)continue;
    frag.append(document.createTextNode(node.textContent.slice(last,start)));
    const a=document.createElement('a');a.className='native-file-link';a.href='#';a.textContent=value;
    a.title='Open matching indexed file in this offline viewer';
    a.dataset.parsedSource=value;
    a.addEventListener('click',event=>{event.preventDefault();void open(value).catch(error=>window.toast?.(error.message));});
    frag.append(a);last=start+value.length;
   }
   frag.append(document.createTextNode(node.textContent.slice(last)));node.replaceWith(frag);
  }
 }
 async function open(name,quiet=false){
  const result=await window.api('/api/linked-source?'+new URLSearchParams({name}));
  const matches=result.matches||[];
  if(!matches.length){if(!quiet)window.toast?.('This file is not yet indexed. Choose its export folder and scan to link it.');return false;}
  if(matches.length===1){await window.openChat(matches[0].id);return true;}
  if(!chooser){chooser=document.createElement('dialog');chooser.className='parsed-file-chooser';
   chooser.setAttribute('aria-label','Choose indexed file');document.body.append(chooser);
  }
  const heading=document.createElement('h3');heading.textContent='Choose the matching saved conversation';
  const note=document.createElement('p');note.className='muted';note.textContent='Several indexed conversations share this filename.';
  chooser.replaceChildren(heading,note);
  for(const match of matches){
   const button=document.createElement('button');button.className='parsed-file-choice';
   button.textContent=match.title+' · '+match.filename;button.onclick=()=>{chooser.close();void window.openChat(match.id).catch(e=>window.toast?.(e.message));};
   chooser.append(button);
  }
  const close=document.createElement('button');close.className='secondary';close.textContent='Cancel';close.onclick=()=>chooser.close();chooser.append(close);
  chooser.showModal();
  return true;
 }
 return {decorate,open};
})();
