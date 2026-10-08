'use strict';
window.RichMedia=(()=>{
 const n=(tag,cls='',text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
 function markup(text){return text.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g).map((part,i)=>i%2?part:part.replace(/<caption>([\s\S]*?)<\/caption>/gi,(_,caption)=>'\n\n'+caption+'\n\n').replace(/<text\b[^>]*>([\s\S]*?)<\/text>/gi,'$1').replace(/<Link\s+url=["'](https?:\/\/[^"'<>]+)["']\s+title=["']([^"'<>]*)["']\s*\/>/gi,(_,url,title)=>'['+title.replace(/[\[\]]/g,'')+'](<'+url+'>)').replace(/^\s*\*{4}\s*$/gm,'' )).join('');}
 function safeUrl(value){if(!value)return '';try{const u=new URL(value,location.href);return /^https?:$/.test(u.protocol)?u.href:'';}catch{return '';}}
 function group(spec,context={}){
  const card=n('section','saved-widget rich-media-group'),grid=n('div','rich-media-grid'),status=n('p','rich-media-status');
  card.append(n('h4','widget-title',spec.title||'Saved image collection'),status,grid);
  let source=spec.images||spec.items||spec.results||spec.query||[];if(!Array.isArray(source))source=[source];let loaded=0,waiting=0,missing=0;
  const update=()=>status.textContent=`${loaded} loaded · ${waiting} loading · ${missing} unavailable`;
  if(!source.length)source=[{title:'Image preview unavailable'}];
  for(const entry of source.slice(0,24)){
   const item=typeof entry==='string'?{title:entry}:entry||{},figure=n('figure','rich-media-card'),preview=n('div','rich-media-preview'),caption=n('figcaption'),title=item.title||item.caption||item.query||'Saved image',raw=item.image_url?.url||item.image_url||item.url||item.src||'',href=safeUrl(item.source_url||item.link||(/^(?:https?:|\/\/)/i.test(raw)?raw:''));
   figure.append(preview,caption);caption.append(n('strong','',title));if(item.description)caption.append(n('small','',item.description));
   const fallback=message=>{preview.classList.remove('loading');preview.replaceChildren(ViewerIcons.svg('image'),n('strong','','Preview unavailable'),n('small','',message));};
   const resolved=raw&&!/^(?:[a-z]+:|\/\/)/i.test(raw)&&context.cid?'/api/asset?'+new URLSearchParams({id:context.cid,path:raw}):raw,url=safeUrl(resolved),local=url&&new URL(url).origin===location.origin&&/^\/api\/(?:asset|thread-images\/content|thread-attachments\/relative)\?/.test(new URL(url).pathname+'?');
   if(local){waiting++;const img=n('img');img.alt=title;img.loading='lazy';img.decoding='async';preview.classList.add('loading');preview.append(img);img.onload=()=>{waiting--;loaded++;preview.classList.remove('loading');update();};img.onerror=()=>{waiting--;missing++;fallback('The saved image could not be loaded.');update();};img.src=url;if(context.cid){img.tabIndex=0;img.setAttribute('role','button');img.title='Open image viewer';const open=()=>ThreadImages.open(context.cid,raw,img,S.leaf).catch(e=>toast(e.message));img.onclick=open;img.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}};}}
   else{missing++;fallback(raw?'This external image was not saved for offline preview.':'The image search is saved; its image files are unavailable.');}
   if(href||local){const a=n('a','','Open source ↗');a.href=href||url;a.target='_blank';a.rel='noopener noreferrer';caption.append(a);}grid.append(figure);
  }
  const details=n('details','widget-source'),summary=n('summary','','Saved source'),pre=n('pre');pre.textContent=JSON.stringify(spec,null,2);details.append(summary,pre);card.append(details);update();return card;
 }
 return {markup,group};
})();
