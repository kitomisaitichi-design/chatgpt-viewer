'use strict';
/* Whole-thread position index: the DOM only contains a bounded page of messages. */
window.ConversationTimeline=(()=>{
 let rail,track,notches=[],preview,role,excerpt,position,items=[],total=0,active=0,selected='',request=0,controller=null,paintPending=false,fadeTimer=null,dragPointer=null;
 const byId=id=>document.getElementById(id);
 const NOTCHES=19;
 function paintNotches(progress){
  const focus=Math.max(0,Math.min(1,progress))*(NOTCHES-1);
  for(let i=0;i<notches.length;i++){
   const distance=Math.abs(i-focus),strength=Math.exp(-distance*distance/7);
   const notch=notches[i];
   notch.style.opacity=String(.17+.76*strength);
  }
 }
 function continuousProgress(){
  const scroller=byId('scroller'),messageList=S.messages||[];
  if(!scroller||!messageList.length||total<=1)return 0;
  const first=Number(messageList[0].seq),last=Number(messageList[messageList.length-1].seq);
  const locate=seq=>{
   let lo=0,hi=items.length-1;
   while(lo<hi){const mid=(lo+hi+1)>>1;if(items[mid].seq<=seq)lo=mid;else hi=mid-1;}
   return items[lo]?.index||0;
  };
  const ratio=Math.max(0,Math.min(1,scroller.scrollTop/Math.max(1,scroller.scrollHeight-scroller.clientHeight)));
  return (locate(first)+(locate(last)-locate(first))*ratio)/(total-1);
 }
 function hide(){
  if(controller){controller.abort();controller=null;}
  request++;selected='';items=[];total=0;active=0;
  clearTimeout(fadeTimer);dragPointer=null;
  byId('main')?.classList.remove('timeline-wide');
  if(rail){rail.hidden=true;rail.classList.remove('previewing','timeline-scrolling','timeline-dragging');}
 }
 function currentIndex(){
  if(!items.length||!S.selected)return 0;
  const rect=byId('scroller')?.getBoundingClientRect();
  let seq;
  if(rect)for(const node of byId('messages').children){
   if(node.getBoundingClientRect().bottom>rect.top+45){seq=Number(node.dataset.seq);break;}
  }
  if(!Number.isFinite(seq))seq=Number(S.messages?.at(-1)?.seq)||items[0].seq;
  let lo=0,hi=items.length-1;
  while(lo<hi){const mid=(lo+hi+1)>>1;if(items[mid].seq<=seq)lo=mid;else hi=mid-1;}
  return lo;
 }
 function setActive(index){
  if(!items.length)return;
  active=Math.max(0,Math.min(items.length-1,index));
  const item=items[active],pct=total>1?item.index/(total-1):0;
  paintNotches(pct);
  rail.setAttribute('aria-valuenow',String(item.index+1));
  rail.setAttribute('aria-valuetext','Message '+(item.index+1)+' of '+total);
 }
 function updateScroll(){
  if(paintPending||!items.length)return;
  rail.classList.add('timeline-scrolling');
  clearTimeout(fadeTimer);
  fadeTimer=setTimeout(()=>rail?.classList.remove('timeline-scrolling'),1100);
  paintPending=true;requestAnimationFrame(()=>{
   paintPending=false;
   if(rail.hidden||dragPointer!==null)return;
   if(!rail.matches(':hover'))setActive(currentIndex());
   paintNotches(continuousProgress());
  });
 }
 function show(index){
  if(!items.length)return;
  setActive(index);const item=items[active];
  role.textContent=(item.role==='user'?'You':item.role==='assistant'?'ChatGPT':item.role)+(item.channel&&item.channel!=='final'?' · '+item.channel:'');
  excerpt.textContent=item.preview;
  position.textContent=(item.index+1).toLocaleString()+' / '+total.toLocaleString();
  const spot=total>1?item.index/(total-1):0;
  rail.classList.add('previewing');
  preview.style.top=Math.max(4,Math.min(track.clientHeight-preview.offsetHeight-4,spot*track.clientHeight-preview.offsetHeight/2))+'px';
 }
 function atPointer(event){
  const rect=track.getBoundingClientRect(),pct=Math.max(0,Math.min(1,(event.clientY-rect.top)/(rect.height||1)));
  const target=pct*Math.max(0,total-1);
  let lo=0,hi=items.length-1;
  while(lo<hi){const mid=(lo+hi)>>1;if(items[mid].index<target)lo=mid+1;else hi=mid;}
  return lo>0&&Math.abs(items[lo-1].index-target)<Math.abs(items[lo].index-target)?lo-1:lo;
 }
 function go(){
  if(!items[active]||!S.selected||!selected.startsWith(S.selected.id+'|'))return;
  const item=items[active],loaded=byId('messages').querySelector('[data-seq="'+item.seq+'"]');
  if(loaded){focusMessage(item.seq);return;}
  openChat(S.selected.id,item.seq,false,S.leaf).catch(error=>toast(error.message));
 }
 function render(){
  if(!total||!items.length){rail.hidden=true;return;}
  rail.hidden=false;rail.setAttribute('aria-valuemax',String(total));setActive(currentIndex());checkRoom();
 }
 function checkRoom(){
  if(!rail||rail.hidden)return;
  const main=byId('main'),conversation=byId('conversation');
  if(!main||!conversation)return;
  const gap=main.getBoundingClientRect().right-conversation.getBoundingClientRect().right;
  const room=innerWidth>=1050&&gap>=78;
  rail.classList.toggle('timeline-has-room',room);
  main.classList.toggle('timeline-wide',room);
 }
 async function refresh(){
  if(!S.selected){hide();return;}
  const key=[S.selected.id,S.leaf||'',S.details?'1':'0'].join('|');
  if(key===selected&&items.length){checkRoom();updateScroll();return;}
  selected=key;const cid=S.selected.id;items=[];total=0;
  if(controller)controller.abort();
  controller=new AbortController();const next=++request;
  rail.hidden=true;rail.classList.remove('previewing');
  try{
   const query=new URLSearchParams({id:cid,details:S.details?'1':'0',...(S.leaf?{leaf:S.leaf}:{})});
   const response=await fetch('/api/timeline?'+query,{signal:controller.signal});
   if(!response.ok)throw Error('Timeline unavailable');
   const data=await response.json();
   if(next!==request||S.selected?.id!==cid)return;
   items=Array.isArray(data.items)?data.items:[];total=Number(data.total)||0;render();
  }catch(error){if(error.name!=='AbortError'&&next===request){rail.hidden=true;byId('main')?.classList.remove('timeline-wide');}}
 }
 function bind(){
  const main=byId('main');if(!main)return;
  rail=document.createElement('aside');rail.id='conversation-timeline';rail.hidden=true;rail.tabIndex=0;rail.setAttribute('role','slider');rail.setAttribute('aria-label','Message scrubber. Hover for a preview; click, drag or press Enter to jump to a message.');rail.setAttribute('aria-orientation','vertical');rail.setAttribute('aria-valuemin','1');
  track=document.createElement('div');track.className='timeline-track';
  for(let i=0;i<NOTCHES;i++){
   const notch=document.createElement('span');
   notch.className='timeline-notch';
   notch.style.top=(i*100/(NOTCHES-1))+'%';
   track.append(notch);notches.push(notch);
  }
  preview=document.createElement('div');preview.className='timeline-preview';
  role=document.createElement('strong');role.className='timeline-preview-role';excerpt=document.createElement('p');excerpt.className='timeline-preview-text';position=document.createElement('small');position.className='timeline-preview-position';
  preview.append(role,excerpt,position);rail.append(track,preview);main.append(rail);
  rail.addEventListener('pointerenter',event=>{if(event.pointerType!=='touch')show(atPointer(event));});
  rail.addEventListener('pointerdown',event=>{
   if(event.button!==0)return;
   dragPointer=event.pointerId;dragged=false;
   rail.setPointerCapture(event.pointerId);rail.classList.add('timeline-dragging');
   show(atPointer(event));event.preventDefault();
  });
  rail.addEventListener('pointermove',event=>{
   if(dragPointer!==null&&event.pointerId!==dragPointer)return;
   if(dragPointer!==null)dragged=true;
   if(event.pointerType!=='touch'||dragPointer!==null)show(atPointer(event));
  });
  rail.addEventListener('pointerup',event=>{
   if(dragPointer!==event.pointerId)return;
   show(atPointer(event));dragPointer=null;rail.classList.remove('timeline-dragging');
   if(rail.hasPointerCapture(event.pointerId))rail.releasePointerCapture(event.pointerId);
   go();
  });
  rail.addEventListener('pointercancel',()=>{dragPointer=null;rail.classList.remove('timeline-dragging','previewing');setActive(currentIndex());});
  rail.addEventListener('pointerleave',()=>{if(dragPointer===null){rail.classList.remove('previewing');setActive(currentIndex());}});
  rail.addEventListener('keydown',event=>{
   if(['ArrowDown','ArrowRight','ArrowUp','ArrowLeft','Home','End','Enter',' '].includes(event.key)){
    event.preventDefault();
    if(event.key==='Enter'||event.key===' '){go();return;}
    const idx=event.key==='Home'?0:event.key==='End'?items.length-1:active+(['ArrowDown','ArrowRight'].includes(event.key)?1:-1);
    show(idx);
   }
  });
  byId('scroller').addEventListener('scroll',updateScroll,{passive:true});
  window.addEventListener('resize',checkRoom,{passive:true});
 }
 document.addEventListener('DOMContentLoaded',bind);
 return{refresh,hide,updateScroll,checkRoom};
})();
