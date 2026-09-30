'use strict';
window.SidebarOrder={
 mergeOrder(visible,all){const selected=new Set(visible);let i=0;return all.map(k=>selected.has(k)?visible[i++]:k);},
 key(c,mode,kind){return c.pinned?'pinned':mode==='folders'?'folder:'+(c.folder||'Root'):mode==='types'?'type:'+kind(c):mode==='none'?'all':c.category?'category:'+c.category:c.project?'project:'+c.project:'uncategorized';},
 compare(a,b,sort,title){const value=sort==='manual'?(a.position||0)-(b.position||0):sort==='oldest'?(a.created||0)-(b.created||0):sort==='title'?title(a).localeCompare(title(b)):sort==='updated'?(b.updated||0)-(a.updated||0):(b.created||0)-(a.created||0);return value||title(a).localeCompare(title(b))||a.id.localeCompare(b.id);},
 groups(catalog,settings,type,mode,showProjects,kind,title,sort){
  const groups=new Map(),key=c=>this.key(c,mode,kind);if(mode==='categories')for(const name of settings.categories||[])groups.set('category:'+name,[]);
  const allKeys=[...new Set(catalog.map(key))].sort((a,b)=>a.localeCompare(b));for(const k of allKeys)if(!groups.has(k))groups.set(k,[]);
  for(const c of catalog)if((type==='all'||kind(c)===type)&&(showProjects||!c.project))groups.get(key(c)).push(c);
  const saved=settings.groupOrder?.[mode]||[];const natural=[...groups.keys()];if(!saved.length&&groups.has('pinned')){natural.splice(natural.indexOf('pinned'),1);natural.unshift('pinned');}
  const order=[...saved.filter(k=>groups.has(k)),...natural.filter(k=>!saved.includes(k))];if(order.includes('pinned')){order.splice(order.indexOf('pinned'),1);order.unshift('pinned');}
  return new Map(order.filter(k=>groups.get(k).length||k.startsWith('category:')).map(k=>[k,groups.get(k).sort((a,b)=>this.compare(a,b,settings.groupSort?.[mode+'|'+k]||(k==='pinned'?'manual':sort),title))]));
 }
};