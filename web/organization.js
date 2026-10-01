'use strict';
window.SidebarOrder={
 collator:new Intl.Collator(undefined,{numeric:true,sensitivity:'base'}),cache:new Map(),
 // Keep a longest increasing subsequence of existing nodes: only the others move.
 stableIndices(sequence){const tails=[],previous=new Array(sequence.length).fill(-1);for(let i=0;i<sequence.length;i++){if(sequence[i]<0)continue;let lo=0,hi=tails.length;while(lo<hi){const mid=(lo+hi)>>1;if(sequence[tails[mid]]<sequence[i])lo=mid+1;else hi=mid;}if(lo)previous[i]=tails[lo-1];tails[lo]=i;}const kept=new Set();let at=tails.at(-1);while(at!==undefined&&at>=0){kept.add(at);at=previous[at];}return kept;},
 reconcile(box,nodes){const wanted=new Set(nodes),before=[...box.children],top=box.getBoundingClientRect().top,anchor=before.find(n=>wanted.has(n)&&n.getBoundingClientRect().bottom>top),offset=anchor?anchor.getBoundingClientRect().top-top:0,scroll=box.scrollTop,indices=new Map(before.map((n,i)=>[n,i])),kept=this.stableIndices(nodes.map(n=>indices.get(n)??-1));for(const n of before)if(!wanted.has(n))n.remove();let next=null;for(let i=nodes.length-1;i>=0;i--){if(!kept.has(i))box.insertBefore(nodes[i],next);next=nodes[i];}if(anchor?.isConnected)box.scrollTop+=anchor.getBoundingClientRect().top-top-offset;else box.scrollTop=scroll;},
 mergeOrder(visible,all){const selected=new Set(visible);let i=0;return all.map(k=>selected.has(k)?visible[i++]:k);},
 key(c,mode,kind){return c.pinned?'pinned':mode==='folders'?'folder:'+(c.folder||'Root'):mode==='types'?'type:'+kind(c):mode==='none'?'all':c.category?'category:'+c.category:c.project?'project:'+c.project:'uncategorized';},
 compare(a,b,sort,title){const value=sort==='manual'?(a.position||0)-(b.position||0):sort==='oldest'?(a.created||0)-(b.created||0):sort==='title'?this.collator.compare(title(a),title(b)):sort==='updated'?(b.updated||0)-(a.updated||0):(b.created||0)-(a.created||0);return value||this.collator.compare(title(a),title(b))||a.id.localeCompare(b.id);},
 groups(catalog,settings,type,mode,showProjects,kind,title,sort){
  const groups=new Map(),key=c=>this.key(c,mode,kind);if(mode==='categories')for(const name of settings.categories||[])groups.set('category:'+name,[]);
  const allKeys=[...new Set(catalog.map(key))].sort((a,b)=>a.localeCompare(b));for(const k of allKeys)if(!groups.has(k))groups.set(k,[]);
  for(const c of catalog)if((type==='all'||kind(c)===type)&&(showProjects||!c.project))groups.get(key(c)).push(c);
  const saved=settings.groupOrder?.[mode]||[];const natural=[...groups.keys()];if(!saved.length&&groups.has('pinned')){natural.splice(natural.indexOf('pinned'),1);natural.unshift('pinned');}
  const order=[...saved.filter(k=>groups.has(k)),...natural.filter(k=>!saved.includes(k))];if(order.includes('pinned')){order.splice(order.indexOf('pinned'),1);order.unshift('pinned');}
  return new Map(order.filter(k=>groups.get(k).length||k.startsWith('category:')).map(k=>{const rows=groups.get(k),choice=settings.groupSort?.[mode+'|'+k]||(k==='pinned'?'manual':sort),cacheKey=[mode,k,type,showProjects,choice].join('|'),signature=JSON.stringify(rows.map(c=>[c.id,title(c),choice==='manual'?c.position:choice==='updated'?c.updated:c.created])),old=this.cache.get(cacheKey);if(old?.signature===signature){const byId=new Map(rows.map(c=>[c.id,c]));return [k,old.ids.map(id=>byId.get(id))];}rows.sort((a,b)=>this.compare(a,b,choice,title));this.cache.set(cacheKey,{signature,ids:rows.map(c=>c.id)});if(this.cache.size>512)this.cache.delete(this.cache.keys().next().value);return [k,rows];}));
 }
};
