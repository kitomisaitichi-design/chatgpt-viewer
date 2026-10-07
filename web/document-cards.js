'use strict';
// Parse only line-level writing enclosures. Code fences and malformed headers
// remain literal. Body Markdown still goes through the normal reader pipeline.
var DocumentCards=(()=>{
 function extract(text){
  const documents=[],out=[],lines=text.split('\n');let fence=null,current=null;
  for(const line of lines){
   const f=line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
   if(f){if(!fence)fence={char:f[1][0],length:f[1].length};else if(f[1][0]===fence.char&&f[1].length>=fence.length&&!f[2].trim())fence=null;out.push(line);if(current)current.body.push(line);continue;}
   if(!fence&&!current){const match=line.match(/^\s*:::writing\s*\{(.*)\}\s*$/);if(match){
    let attrs;try{attrs=JSON.parse('{'+match[1]+'}');}catch{attrs={};const re=/(\w+)\s*=\s*("(?:\\.|[^"\\])*"|'[^']*')/g;let a;while((a=re.exec(match[1]))){try{attrs[a[1]]=a[2][0]==='"'?JSON.parse(a[2]):a[2].slice(1,-1);}catch{}}if(match[1].replace(re,'').trim())attrs={};}
    if(['document','email','essay'].includes(attrs.variant)){current={title:String(attrs.title||'Saved document'),body:[],index:documents.length};documents.push(current);out.push('\nOFFLINEDOCUMENTSTART'+current.index+'END\n');continue;}
   }}
   if(!fence&&current&&/^\s*:::\s*$/.test(line)){out.push('\nOFFLINEDOCUMENTSTOP'+current.index+'END\n');current=null;continue;}
   out.push(line);if(current)current.body.push(line);
  }
  if(current)out.push('\nOFFLINEDOCUMENTSTOP'+current.index+'END\n');
  return {text:out.join('\n'),documents:documents.map(d=>({...d,body:d.body.join('\n')}))};
 }
 function decorate(root,documents,partial=false){
  for(const doc of documents){
   const start=[...root.querySelectorAll('p')].find(p=>p.textContent.trim()==='OFFLINEDOCUMENTSTART'+doc.index+'END'),end=[...root.querySelectorAll('p')].find(p=>p.textContent.trim()==='OFFLINEDOCUMENTSTOP'+doc.index+'END');if(!start||!end)continue;
   const range=document.createRange();range.setStartAfter(start);range.setEndBefore(end);const body=document.createElement('div');body.className='document-body';body.append(range.extractContents());
   const card=document.createElement('section');card.className='document-card';const header=document.createElement('header'),title=document.createElement('span'),copy=document.createElement('button'),expand=document.createElement('button');header.className='document-header';title.textContent=doc.title;copy.textContent='⧉';copy.title=partial?'Copy loaded document':'Copy document';copy.setAttribute('aria-label',copy.title);expand.textContent='⤢';expand.title='Expand document';expand.setAttribute('aria-label','Expand document');
   copy.onclick=async()=>{try{await navigator.clipboard.writeText(doc.body);copy.textContent='✓';setTimeout(()=>copy.textContent='⧉',1200);}catch(error){toast('Could not copy document: '+error.message);}};
   expand.onclick=()=>{expand.disabled=true;const spacer=document.createElement('div');const style=getComputedStyle(card);spacer.style.height=card.getBoundingClientRect().height+'px';spacer.style.margin=style.margin;spacer.setAttribute('aria-hidden','true');card.before(spacer);const dialog=document.createElement('dialog');dialog.className='document-dialog message';const close=document.createElement('button');close.className='document-close';close.textContent='Close ×';close.onclick=()=>dialog.close();dialog.append(close,card);document.body.append(dialog);dialog.addEventListener('close',()=>{spacer.replaceWith(card);expand.disabled=false;dialog.remove();expand.focus({preventScroll:true});},{once:true});dialog.showModal();};
   header.append(title,copy,expand);card.append(header,body);start.after(card);start.hidden=true;end.remove();
  }
 }
 return {extract,decorate};
})();
