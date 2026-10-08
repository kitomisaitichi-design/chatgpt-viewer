'use strict';
// Shared offset matching for document previews and their sandbox/worker.
globalThis.DocumentSearch=(()=>{
 const word=character=>!!character&&/[\p{L}\p{N}_]/u.test(character);
 function match(segments,query,options={}){
  if(!query)return {hits:[],limited:false};
  if(query.length>500)throw Error('Search text is limited to 500 characters.');
  const source=options.regex?query:query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  let pattern;try{pattern=new RegExp(source,options.caseSensitive?'gu':'giu');}catch{throw Error('Invalid regular expression. Check the pattern and try again.');}
  const hits=[];
  for(let segment=0;segment<segments.length;segment++){
   const text=segments[segment].text;pattern.lastIndex=0;let found;
   while((found=pattern.exec(text))){
    if(!found[0].length){pattern.lastIndex+=text.codePointAt(pattern.lastIndex)>0xffff?2:1;continue;}
    const start=found.index,end=start+found[0].length;
    if(options.wholeWord&&(word([...text.slice(Math.max(0,start-2),start)].pop())||word(String.fromCodePoint(text.codePointAt(end)||0))))continue;
    hits.push({segment,start,end});if(hits.length>=10000)return {hits,limited:true};
   }
  }
  return {hits,limited:false};
 }
 function snapshot(root,separator=''){
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];let text='';
  while(walker.nextNode()){
   const node=walker.currentNode;if(!node.textContent||node.parentElement?.closest('script,style,button,select,[hidden]'))continue;
   if(nodes.length)text+=separator;nodes.push({node,start:text.length,end:text.length+node.textContent.length});text+=node.textContent;
  }
  function locate(offset,end=false){let lo=0,hi=nodes.length;while(lo<hi){const mid=(lo+hi)>>1;if(end?nodes[mid].end<offset:nodes[mid].end<=offset)lo=mid+1;else hi=mid;}return nodes[lo];}
  return {text,range(hit){const first=locate(hit.start),last=locate(hit.end,true);if(!first||!last)return null;const range=document.createRange();range.setStart(first.node,Math.max(0,hit.start-first.start));range.setEnd(last.node,hit.end-last.start);return range;}};
 }
 function clear(){if(globalThis.CSS?.highlights){CSS.highlights.delete('document-matches');CSS.highlights.delete('document-current');}}
 function paint(snapshot,hits,index,all=true,scroller=null,reveal=true){
  clear();const selected=hits[index],range=selected&&snapshot.range(selected);if(!range)return;
  if(globalThis.CSS?.highlights&&globalThis.Highlight){if(all)CSS.highlights.set('document-matches',new Highlight(...hits.map(h=>snapshot.range(h)).filter(Boolean)));CSS.highlights.set('document-current',new Highlight(range));}
  else{const selection=getSelection();selection.removeAllRanges();selection.addRange(range);}
  if(reveal){for(let p=range.startContainer.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;const rect=range.getBoundingClientRect();if(scroller){const box=scroller.getBoundingClientRect();scroller.scrollTo({top:scroller.scrollTop+rect.top-box.top-scroller.clientHeight/2,left:Math.max(0,scroller.scrollLeft+rect.left-box.left-scroller.clientWidth/2),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}else globalThis.scrollTo({top:scrollY+rect.top-innerHeight/2,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
 }
 return {match,snapshot,paint,clear};
})();
