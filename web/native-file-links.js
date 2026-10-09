'use strict';
/* Cross-link saved source filenames to the conversation already indexed from them.
 * Never opens an arbitrary file:// URL or a path supplied by chat content. */
window.NativeFileLinks=(()=>{
 const names=/(?:[A-Za-z]:[\\/])?(?:[\w.@+()\-]+[\\/])*[\w.@+()\-]+\.(?:jsonl|json|md)\b/gi;
 const prohibited='a,button,pre,code,kbd,samp,textarea,script,style,.saved-widget,.source-refs';
 let chooser=null;
 const basename=value=>String(value).replace(/\\/g,'/').split('/').at(-1).toLowerCase();
 function candidates(text){
  if(typeof text!=='string'||text.length>131072||!(/\.(?:jsonl|json|md)\b/i.test(text)))return [];
  return [...text.matchAll(names)].filter(m=>m[0].length<=400&&!(m.index>0&&/[:/]/.test(text.slice(Math.max(0,m.index-3),m.index)))).slice(0,35);
 }
 function decorate(root){
  if(!root)return;
  // Markdown's sanitized relative links already point at /api/asset. Prefer
  // opening their indexed conversation, but preserve the original download
  // when no matching parsed chat exists.
  for(const anchor of root.querySelectorAll('a')){
   if(anchor.dataset.parsedSource)continue;
   let reference='',fallback='';
   if(anchor.hasAttribute('href')){
    let url;try{url=new URL(anchor.getAttribute('href'),location.href);}catch{continue;}
    if(url.origin!==location.origin||url.pathname!=='/api/asset')continue;
    reference=url.searchParams.get('path')||'';fallback=url.href;
   }else{
    // The Markdown sanitizer strips Windows C:\... href values because
    // browsers mistake their drive letters for URL schemes. Those displayed
    // anchors were previously inert even when the file was indexed.
    reference=anchor.dataset.indexedSource||anchor.textContent.trim();
   }
   if(!candidates(reference).some(match=>basename(match[0])===basename(reference)))continue;
   anchor.classList.add('native-file-link');anchor.title='Preview the saved file in this viewer';
   anchor.dataset.parsedSource=reference;
   if(!anchor.hasAttribute('href'))anchor.href='#';
   anchor.addEventListener('click',event=>{
    event.preventDefault();
    void open(reference,!(!fallback)).then(found=>{if(!found&&fallback)window.open(fallback,'_blank','noopener,noreferrer');})
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
 async function preview(match,reference){
  const cid=typeof S==='undefined'?null:S.selected?.id,leaf=typeof S==='undefined'?null:S.leaf;
  if(cid&&window.ThreadAttachments?.catalog&&window.ThreadAttachments?.open){
   // A source can be both the parsed conversation AND a real linked
   // attachment in that same conversation. Reopening the selected chat was
   // an invisible no-op; the file pane must win here.
   const data=await window.ThreadAttachments.catalog(cid,leaf);
   const normalized=String(reference).replace(/\\/g,'/').toLowerCase();
   const exact=(data.attachments||[]).find(file=>file.available&&
     file.references?.some(ref=>String(ref).replace(/\\/g,'/').toLowerCase()===normalized));
   const item=exact||(!/[\\/]/.test(reference)&&(data.attachments||[]).find(
     file=>file.available&&basename(file.name)===basename(reference)));
   if(item){await window.ThreadAttachments.open(cid,item.id,null,leaf);return;}
  }
  if(match.id===cid){
   // Even an indexed source that was not listed as an attachment must have
   // a visible action rather than reopen the already-selected conversation.
   window.open('/api/source?'+new URLSearchParams({id:match.id}),'_blank','noopener,noreferrer');
  }else await window.openChat(match.id);
 }
 async function open(name,quiet=false){
  const result=await window.api('/api/linked-source?'+new URLSearchParams({name}));
  const matches=result.matches||[];
  if(!matches.length){if(!quiet)window.toast?.('This file is not yet indexed. Choose its export folder and scan to link it.');return false;}
  if(matches.length===1){await preview(matches[0],name);return true;}
  if(!chooser){chooser=document.createElement('dialog');chooser.className='parsed-file-chooser';
   chooser.setAttribute('aria-label','Choose indexed file');document.body.append(chooser);
  }
  const heading=document.createElement('h3');heading.textContent='Choose the matching saved conversation';
  const note=document.createElement('p');note.className='muted';note.textContent='Several indexed conversations share this filename.';
  chooser.replaceChildren(heading,note);
  for(const match of matches){
   const button=document.createElement('button');button.className='parsed-file-choice';
   button.textContent=match.title+' · '+match.filename;button.onclick=()=>{chooser.close();void preview(match,name).catch(e=>window.toast?.(e.message));};
   chooser.append(button);
  }
  const close=document.createElement('button');close.className='secondary';close.textContent='Cancel';close.onclick=()=>chooser.close();chooser.append(close);
  chooser.showModal();
  return true;
 }
 return {decorate,open};
})();
