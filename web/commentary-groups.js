'use strict';
/* Keep original message elements/seq IDs. Group only contiguous assistant commentary. */
window.CommentaryGroups=(()=>{
 const classes=['commentary-first','commentary-middle','commentary-last','commentary-single'];
 const commentary=m=>m?.role==='assistant'&&m?.channel==='commentary'&&m?.visible!==false;
 function apply(root,messages){
  if(!root||!messages)return;
  const map=new Map(messages.map(m=>[String(m.seq),m]));
  const nodes=Array.from(root.children).filter(n=>n.matches?.('article.message'));
  for(const node of nodes){
   node.classList.remove(...classes);
   node.querySelector('.commentary-count')?.remove();
   node.querySelector('.commentary-step')?.remove();
   for(const b of node.querySelectorAll(':scope > .message-tools > .model-badge'))b.hidden=false;
  }
  let i=0;
  while(i<nodes.length){
   const first=map.get(nodes[i].dataset.seq);
   if(!commentary(first)){i++;continue;}
   let end=i+1;
   while(end<nodes.length&&commentary(map.get(nodes[end].dataset.seq)))end++;
   const length=end-i;
   if(length<2){nodes[i].classList.add('commentary-single');i=end;continue;}
   const group=nodes.slice(i,end);
   for(let j=0;j<length;j++){
    const node=group[j],start=j===0,finish=j===length-1;
    node.classList.add(start?'commentary-first':finish?'commentary-last':'commentary-middle');
    if(start){
     const label=node.querySelector('.message-label');
     if(label){const count=document.createElement('span');count.className='commentary-count';count.textContent=length+' updates';label.append(count);}
    }else{
     const summary=node.querySelector('.message-summary'),tag=document.createElement('span');
     tag.className='commentary-step';tag.textContent='Update '+(j+1)+' of '+length;
     summary?.append(tag);
    }
   }
   // Preserve each distinct recorded model/effort label, but display repeats once at the last occurrence.
   const seen=new Set();
   for(let j=length-1;j>=0;j--){
    const badge=group[j].querySelector(':scope > .message-tools > .model-badge');
    if(!badge)continue;
    const signature=badge.textContent.trim();
    if(seen.has(signature))badge.hidden=true;
    else seen.add(signature);
   }
   i=end;
  }
 }
 return {apply};
})();
