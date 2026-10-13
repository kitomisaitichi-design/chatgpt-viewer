'use strict';
// Catalog-only filtering never reads messages or changes the user's group order.
window.CatalogModel=(()=>{
 const normalize=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase();
 const timestamp=value=>Number.isFinite(Number(value))&&Number(value)>0?Number(value):0;
 const records=new WeakMap();
 function record(c,title=c=>c.alias||c.title||''){
  const shown=title(c)||'';let value=records.get(c);
  if(value&&value.shown===shown&&value.original===c.title&&value.project===c.project&&value.category===c.category&&value.folder===c.folder&&value.identity===c.id)return value;
  const names=[normalize(shown),normalize(c.title||'')];value={shown,original:c.title,project:c.project,category:c.category,folder:c.folder,identity:c.id,names,id:normalize(c.id),search:normalize([shown,c.title,c.project,c.category,c.folder].join(' ')),words:[...new Set(names.join(' ').match(/[\p{L}\p{N}]+/gu)||[])]};records.set(c,value);return value;
 }
 function distance(a,b,limit){
  if(Math.abs(a.length-b.length)>limit)return limit+1;let previous=Array.from({length:b.length+1},(_,i)=>i);
  for(let i=1;i<=a.length;i++){const row=[i];let best=i;for(let j=1;j<=b.length;j++){row[j]=Math.min(row[j-1]+1,previous[j]+1,previous[j-1]+(a[i-1]===b[j-1]?0:1));best=Math.min(best,row[j]);}if(best>limit)return limit+1;previous=row;}return previous[b.length];
 }
 function lookup(chats,query,{limit=40,typos=true,title=c=>c.alias||c.title||'',kind=null,type='all',category='all'}={}){
  const q=normalize(query).trim().replace(/\s+/g,' ');if(!q)return [];
  const words=q.match(/[\p{L}\p{N}]+/gu)||[],hits=[],possible=[];const similar=new Map(),cap=Math.max(1,Math.min(240,limit));
  const compare=(a,b)=>a.score-b.score||b.updated-a.updated||(a.cid<b.cid?-1:a.cid>b.cid?1:0);
  const keep=hit=>{let low=0,high=hits.length;while(low<high){const middle=(low+high)>>>1;if(compare(hit,hits[middle])<0)high=middle;else low=middle+1;}if(low<cap){hits.splice(low,0,hit);if(hits.length>cap)hits.pop();}};
  for(const c of chats){
   if(c.trashed||type!=='all'&&(kind?kind(c):c.kind)!==type||category!=='all'&&(c.category||'')!==category)continue;
   const r=record(c,title);let score=Infinity,match='Title match';
   if(r.id===q)score=0;
   for(let i=0;i<r.names.length;i++){const name=r.names[i];if(name===q)score=Math.min(score,i);else if(name.startsWith(q))score=Math.min(score,2+i);else if(name.includes(q))score=Math.min(score,4+i);}
   if(score>5&&words.length&&words.every(word=>r.words.some(w=>w.startsWith(word))))score=Math.min(score,6);
   if(score>7&&words.length&&words.every(word=>r.words.some(w=>w.includes(word))))score=Math.min(score,8);
   if(Number.isFinite(score))keep({cid:c.id,seq:-1,title:title(c),snippet:title(c),score,match,updated:Number(c.updated||c.created)||0});
   else if(typos&&q.length>=4&&words.length<=5&&possible.length<400&&words.every(word=>r.words.some(w=>w[0]===word[0]&&Math.abs(w.length-word.length)<=2)))possible.push({c,r});
  }
  // Fuzzy work is bounded and only used when literal title matches are absent.
  if(!hits.length)for(const {c,r} of possible){let cost=0,valid=!!words.length;
   for(const word of words){let best=3;for(const candidate of r.words){if(candidate[0]!==word[0]||word.length<4||candidate.length>64)continue;const key=word+'|'+candidate;let d=similar.get(key);if(d===undefined){d=distance(word,candidate,word.length>7?2:1);similar.set(key,d);}best=Math.min(best,d);}if(best>(word.length>7?2:1)){valid=false;break;}cost+=best;}
   if(valid)keep({cid:c.id,seq:-1,title:title(c),snippet:title(c),score:20+cost,match:'Similar title',updated:Number(c.updated||c.created)||0});
  }
  return hits;
 }
 function isSubagent(chat){return chat.kind==='codex'&&(chat.is_subagent===true||chat.is_subagent===1);}
 function isRead(chat,reads={}){const entry=reads[chat.id];return !!entry&&timestamp(entry.updated)>=timestamp(chat.updated||chat.created);}
 function dayBoundary(value,next=false){if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return null;const [y,m,d]=value.split('-').map(Number),date=new Date(y,m-1,d);if(date.getFullYear()!==y||date.getMonth()!==m-1||date.getDate()!==d)return null;if(next)date.setDate(date.getDate()+1);return date.getTime()/1000;}
 function filter(chats,{query='',read='all',pinned=false,projects='all',untitled=false,field='updated',from='',to='',hideSubagents=false}={},reads={},title=c=>c.alias||c.title||''){
  const words=normalize(query).trim().split(/\s+/).filter(Boolean),start=dayBoundary(from),end=dayBoundary(to,true);
  return chats.filter(c=>{
   if(hideSubagents&&isSubagent(c)||c.trashed||pinned&&!c.pinned||projects==='only'&&!c.project||projects==='none'&&c.project)return false;
   if(read==='read'&&!isRead(c,reads)||read==='unread'&&isRead(c,reads))return false;
   if(untitled&&!/^(?:new chat|untitled(?: conversation)?|chatgpt)?$/i.test(String(title(c)).trim()))return false;
   const time=timestamp(c[field==='created'?'created':'updated']);if((start!==null||end!==null)&&(!time||start!==null&&time<start||end!==null&&time>=end))return false;
   if(words.length){const text=record(c,title).search;if(!words.every(word=>text.includes(word)))return false;}
   return true;
  });
 }
 return {filter,isSubagent,isRead,dayBoundary,normalize,lookup};
})();
