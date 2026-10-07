'use strict';
// Presentation rules never change source metadata or native project membership.
window.SidebarModel=(()=>{
 const labels={pins:'Pinned',projects:'ChatGPT Projects',categories:'My folders & categories',bookmarks:'Bookmarks',folders:'Source folders',chat:'Chats',work:'Work',codex:'Codex'};
 const defaults=()=>({version:1,rules:Object.keys(labels).map(id=>({id,enabled:id!=='folders',depth:0})),limit:3,compact:false,counts:true,empty:true,pinsFirst:true,collapsedFolders:true,closed:[],opened:[],expanded:[]});
 function config(value){const base=defaults(),seen=new Set(),rules=[];for(const item of Array.isArray(value?.rules)?value.rules:base.rules){if(!labels[item.id]||seen.has(item.id))continue;seen.add(item.id);rules.push({id:item.id,enabled:item.enabled!==false,depth:Math.max(0,Math.min(3,Number(item.depth)||0,rules.length?rules.at(-1).depth+1:0))});}for(const item of base.rules)if(!seen.has(item.id))rules.push(item);const c={...base,...value,rules};c.limit=[3,5,8,12,0].includes(Number(c.limit))?Number(c.limit):5;for(const key of ['closed','opened','expanded'])c[key]=Array.isArray(c[key])?c[key].filter(x=>typeof x==='string'):[];return c;}
 function sourceLabel(path,kind){const parts=String(path||'').replace(/\\/g,'/').split('/').filter(Boolean);if(kind==='codex'||parts.some(x=>x.toLowerCase()==='.codex'))return 'Codex sessions';while(parts.length&&(/^(json|markdown|chats?|conversations?|exports?|\d{2,4}|sessions|archived_sessions)$/i.test(parts.at(-1))))parts.pop();let name=parts.at(-1)||'';if(!name||/^chatgpt-backup[-_]/i.test(name))return 'ChatGPT archive';return name.replace(/[_-]+/g,' ');}
 function tree(catalog,settings,type,showProjects,kind,title,sort){
  const cfg=config(settings.sidebarLayout),rows=catalog.filter(c=>!c.trashed&&(type==='all'||kind(c)===type)&&(showProjects||!c.project));
  let rules=cfg.rules.map(r=>({...r,children:[]}));if(cfg.pinsFirst){const pin=rules.find(r=>r.id==='pins'&&r.enabled);if(pin){rules=rules.filter(r=>r!==pin);pin.depth=0;rules.unshift(pin);}}
  const roots=[],stack=[];for(const rule of rules){while(stack.length&&stack.at(-1).depth>=rule.depth)stack.pop();(stack.length?stack.at(-1).children:roots).push(rule);stack.push(rule);}
  function build(input,rules,parent='root'){
   let rest=[...input];const result=[];
   for(const rule of rules){if(!rule.enabled){const promoted=build(rest,rule.children,parent);result.push(...promoted.nodes);rest=promoted.rest;continue;}const matches=c=>rule.id==='pins'?!!c.pinned:rule.id==='bookmarks'?!!c.bookmarked:rule.id==='projects'?!!c.project:rule.id==='categories'?!!c.category:rule.id==='folders'?true:kind(c)===rule.id;
    const selected=rest.filter(matches);rest=rest.filter(c=>!matches(c));const key=parent+'/'+rule.id,node={key,label:labels[rule.id],rule:rule.id,rows:[],children:[],section:true};
    if(['projects','categories','folders'].includes(rule.id)){
     const buckets=new Map();if(rule.id==='categories'&&cfg.empty)for(const name of settings.categories||[])buckets.set(name,[]);if(rule.id==='projects'&&cfg.empty)for(const c of input)if(c.project)buckets.set(c.project,[]);
     for(const c of selected){const value=rule.id==='projects'?c.project:rule.id==='categories'?c.category:sourceLabel(c.folder,kind(c));if(!buckets.has(value))buckets.set(value,[]);buckets.get(value).push(c);}
     for(const [value,items] of [...buckets].sort((a,b)=>window.SidebarOrder.collator.compare(a[0],b[0]))){const childKey=key+'/'+encodeURIComponent(value),nested=build(items,rule.children,childKey);node.children.push({key:childKey,label:value,rule:rule.id,category:rule.id==='categories'?value:null,source:rule.id==='folders'?[...new Set(items.map(c=>c.folder))].join('\n'):'',rows:nested.rest,children:nested.nodes,folder:true});}
    }else{const nested=build(selected,rule.children,key);node.rows=nested.rest;node.children=nested.nodes;}
    if(selected.length||node.children.length||cfg.empty)result.push(node);
   }
   return {nodes:result,rest};
  }
  const built=build(rows,roots);if(built.rest.length)built.nodes.push({key:'root/recent',label:'Recent chats',rule:'recent',rows:built.rest,children:[],section:true});
  const decorate=nodes=>{for(const n of nodes){decorate(n.children);n.count=n.rows.length+n.children.reduce((sum,c)=>sum+c.count,0);const legacy=n.rule==='projects'?'projects|project:'+n.label:n.rule==='categories'?'categories|category:'+n.label:n.rule==='pins'?(settings.group||'projects')+'|pinned':'';const choice=settings.groupSort?.['overview|'+n.key]||settings.groupSort?.[legacy]||(n.rule==='pins'?'manual':sort);n.rows.sort((a,b)=>window.SidebarOrder.compare(a,b,choice,title));const saved=settings.groupOrder?.['overview|'+n.key]||[];const oldOrder=settings.groupOrder?.[n.rule]||[];const position=child=>saved.length?saved.indexOf(child.key):oldOrder.indexOf((n.rule==='projects'?'project:':'category:')+child.label);n.children.sort((a,b)=>{const i=position(a),j=position(b);return i<0&&j<0?0:i<0?1:j<0?-1:i-j;});}};decorate(built.nodes);
  return {nodes:built.nodes,rows,config:cfg};
 }
 return {labels,defaults,config,sourceLabel,tree};
})();
