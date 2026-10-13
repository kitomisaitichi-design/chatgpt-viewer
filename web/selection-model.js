'use strict';
window.ConversationSelectionModel=(()=>{
 function click(selected,anchor,order,id,{ctrl=false,shift=false,toggle=false}={}){
  const next=new Set(selected),at=order.indexOf(id),start=order.indexOf(anchor);
  if(at<0)return {selected:next,anchor};
  if(shift&&start>=0){if(!ctrl)next.clear();for(const key of order.slice(Math.min(start,at),Math.max(start,at)+1))next.add(key);return {selected:next,anchor};}
  if(ctrl||toggle||shift){next.has(id)?next.delete(id):next.add(id);return {selected:next,anchor:id};}
  return {selected:new Set(),anchor:id};
 }
 function invert(selected,order){return new Set(order.filter(id=>!selected.has(id)));}
 return {click,invert};
})();
