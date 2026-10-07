'use strict';
// Catalog-only filtering never reads messages or changes the user's group order.
window.CatalogModel=(()=>{
 const normalize=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase();
 const timestamp=value=>Number.isFinite(Number(value))&&Number(value)>0?Number(value):0;
 function isRead(chat,reads={}){const entry=reads[chat.id];return !!entry&&timestamp(entry.updated)>=timestamp(chat.updated||chat.created);}
 function dayBoundary(value,next=false){if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return null;const [y,m,d]=value.split('-').map(Number),date=new Date(y,m-1,d);if(date.getFullYear()!==y||date.getMonth()!==m-1||date.getDate()!==d)return null;if(next)date.setDate(date.getDate()+1);return date.getTime()/1000;}
 function filter(chats,{query='',read='all',pinned=false,projects='all',untitled=false,field='updated',from='',to=''}={},reads={},title=c=>c.alias||c.title||''){
  const words=normalize(query).trim().split(/\s+/).filter(Boolean),start=dayBoundary(from),end=dayBoundary(to,true);
  return chats.filter(c=>{
   if(c.trashed||pinned&&!c.pinned||projects==='only'&&!c.project||projects==='none'&&c.project)return false;
   if(read==='read'&&!isRead(c,reads)||read==='unread'&&isRead(c,reads))return false;
   if(untitled&&!/^(?:new chat|untitled(?: conversation)?|chatgpt)?$/i.test(String(title(c)).trim()))return false;
   const time=timestamp(c[field==='created'?'created':'updated']);if((start!==null||end!==null)&&(!time||start!==null&&time<start||end!==null&&time>=end))return false;
   if(words.length){const text=normalize([title(c),c.title,c.project,c.category,c.folder].join(' '));if(!words.every(word=>text.includes(word)))return false;}
   return true;
  });
 }
 return {filter,isRead,dayBoundary,normalize};
})();
