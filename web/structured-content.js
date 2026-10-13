'use strict';
// Render saved ChatGPT declarative content without evaluating exported JSX.
// The parser is data-driven: neither node labels nor chart values are templates.
window.StructuredContent=(()=>{
 const NODE=/^[A-Za-z_][\w.-]*/;
 const DIRECTION=/^(?:flowchart|graph)\s+(TD|TB|BT|LR|RL)\b/i;
 const ROOT=/^(?:grid|flow|row|col|box|card|table|data-table|progress|progress-bar|meter|bar|bars|comparison|copy|copyable|code-block|button|tabs|accordion|details|columns|column|newspaper|section|article|panel|stack|status|status-badge)$/i;
 const TAGS=new Set(['grid','grid-item','flow','flow-item','row','col','box','card','text','title','caption','bold','strong','small','badge','divider','spacer','table','data-table','table-section','table-row','table-cell','table-head','table-body','table-footer','thead','tbody','tfoot','tr','th','td','link','progress','progress-bar','meter','bar','bars','comparison','copy','copyable','code-block','button','tabs','tab','tab-panel','accordion','details','summary','chart','label','value','list','list-item','code','columns','column','newspaper','section','article','panel','stack','heading','paragraph','status','status-badge','icon']);
 const n=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
 const svg=(tag,attrs={},text)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=String(text);return e;};
 function readTag(input,at){
  if(input[at]!=='<')return null;
  let quote='',depth=0,i=at+1;
  for(;i<input.length&&i<at+260000;i++){const c=input[i],prev=input[i-1];
   if(quote){if(c===quote&&prev!=='\\')quote='';continue;}
   if(c==='"'||c==="'"){quote=c;continue;}
   if(c==='{')depth++;else if(c==='}')depth=Math.max(0,depth-1);
   else if(c==='>'&&!depth)break;
  }
  if(i===input.length||i>=at+260000)return null;
  const raw=input.slice(at,i+1),m=raw.match(/^<\s*(\/?)\s*([A-Za-z][\w-]*)\b/);
  return m?{raw,name:m[2].toLowerCase(),close:!!m[1],self:/\/\s*>$/.test(raw),end:i+1}:null;
 }
 function attrs(tag){
  const values=Object.create(null),head=tag.match(/^<\s*\/?\s*[\w-]+/);let i=head?.[0].length||0;
  while(i<tag.length){
   while(/\s/.test(tag[i]||'\0'))i++;
   const key=tag.slice(i).match(/^[\w-]+/);if(!key)break;i+=key[0].length;
   while(/\s/.test(tag[i]||'\0'))i++;
   const name=key[0].toLowerCase();if(tag[i]!=='='){values[name]='true';continue;}i++;
   while(/\s/.test(tag[i]||'\0'))i++;
   const opening=tag[i];let value='';
   if(opening==='"'||opening==="'"){
    i++;while(i<tag.length){if(tag[i]===opening){i++;break;}if(tag[i]==='\\'&&tag[i+1]===opening)i++;value+=tag[i++];}
   }else if(opening==='{'){
    const begin=++i;let depth=1,quote='',escaped=false;
    for(;i<tag.length;i++){const c=tag[i];if(quote){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c===quote)quote='';continue;}if(c==='"'||c==="'")quote=c;else if(c==='{')depth++;else if(c==='}'&&!--depth)break;}
    value=tag.slice(begin,i).trim();i++;
    try{const parsed=JSON.parse(value);value=parsed&&typeof parsed==='object'?parsed:parsed===null?'':String(parsed);}catch{ /* Expressions remain inert text, never executable JavaScript. */ }
   }else{const bare=tag.slice(i).match(/^[^\s/>]+/);if(!bare)break;value=bare[0];i+=value.length;}
   values[name]=value;
  }
  return values;
 }
 function layout(input,at){
  const first=readTag(input,at);if(!first||first.close||!ROOT.test(first.name))return null;
  const root={type:first.name,attrs:attrs(first.raw),children:[]},stack=[root];let pos=first.end;
  if(first.self)return {value:root,end:pos,raw:first.raw};
  for(let count=0;pos<input.length&&count<8000;count++){
   const start=input.indexOf('<',pos);
   if(start<0)return null;
   if(start>pos)stack.at(-1).children.push(input.slice(pos,start));
   const tag=readTag(input,start);
   if(!tag||stack.length>64)return null;
   if(tag.close){
    if(stack.at(-1).type!==tag.name)return null;
    stack.pop();pos=tag.end;
    if(!stack.length)return {value:root,end:pos,raw:input.slice(at,pos)};
   }else{
    if(tag.name==='chart'){
     const nested=chart(input,start);
     if(nested){stack.at(-1).children.push({type:'chart',chart:nested.value,children:[]});pos=nested.end;continue;}
    }
    const child={type:tag.name,attrs:attrs(tag.raw),children:[]};
    stack.at(-1).children.push(child);if(!tag.self)stack.push(child);pos=tag.end;
   }
  }
  return null;
 }
 function chart(input,at){
  const tag=readTag(input,at);
  if(!tag||tag.name!=='chart'||tag.close||!tag.self)return null;
  const attr=tag.raw.match(/\bcontent\s*=\s*\{/);
  if(!attr)return null;
  const start=attr.index+attr[0].length-1,expr=tag.raw.slice(start,-2).trim();
  if(expr[0]!=='{'||expr.at(-1)!=='}')return null;
  try{
   const obj=JSON.parse(expr.slice(1,-1).trim());
   if(!obj||!['line','area','bar','scatter','pie'].includes(obj.chartType)||!Array.isArray(obj.data)||!Array.isArray(obj.series)||obj.data.length>100000)return null;
   return {value:obj,end:tag.end,raw:tag.raw};
  }catch{return null;}
 }
 function readNode(input,at){
  let pos=at;while(/[ \t\r\n]/.test(input[pos]||'\0'))pos++;
  const m=input.slice(pos).match(NODE);if(!m)return null;
  let id=m[0];
  // Mermaid permits both spaced and compact links: A --> B, A-->B, A-.->B.
  // Do not absorb the start of an arrow into an unquoted node identifier.
  const boundary=id.search(/--|-\.-/);if(boundary>0)id=id.slice(0,boundary);
  if(!id)return null;
  pos+=id.length;const opening=input[pos];
  let label=id,style='';
  if(['[','(','{'].includes(opening)){
   const close={'[':']','(':')','{':'}'}[opening],start=pos;
   let depth=0,quote='',end=-1;
   for(;pos<input.length&&pos<start+3000;pos++){
    const c=input[pos];if(quote){if(c===quote&&input[pos-1]!=='\\')quote='';continue;}
    if(c==='"'||c==="'"){quote=c;continue;}
    if(c===opening)depth++;
    if(c===close&&!--depth){end=pos+1;break;}
   }
   if(end<0)return null;
   let inside=input.slice(start+1,end-1);
   if(inside.startsWith(opening)&&inside.endsWith(close))inside=inside.slice(1,-1);
   label=inside.replace(/^["']|["']$/g,'').replace(/<br\s*\/?\s*>/gi,'\n').replace(/\\n/g,'\n').replace(/\\(["'])/g,'$1');
   style=opening;pos=end;
  }
  return {id,label,style,end:pos};
 }
 function graph(input){
  const direction=input.match(DIRECTION);
  if(!direction)return null;
  const nodes=new Map(),edges=[],seen=new Set();
  let i=direction[0].length,lastEnd=i,limit=0;
  function keep(item){if(!nodes.has(item.id))nodes.set(item.id,{id:item.id,label:item.label,style:item.style});else if(item.label!==item.id)nodes.set(item.id,{id:item.id,label:item.label,style:item.style});}
  while(i<input.length&&limit++<1400&&edges.length<300&&nodes.size<160){
   const from=readNode(input,i);
   if(!from){i++;continue;}
   let pos=from.end;while(/[ \t\r\n]/.test(input[pos]||'\0'))pos++;
   const edge=input.slice(pos).match(/^(-->|==>|-\.->|---)(?:\|([^|\n]{1,120})\|)?/);
   if(!edge){i=Math.max(i+1,from.end);continue;}
   const to=readNode(input,pos+edge[0].length);
   if(!to){i=pos+edge[0].length;continue;}
   keep(from);keep(to);
   const key=from.id+'|'+to.id+'|'+edge[1]+'|'+(edge[2]||'');
   if(!seen.has(key)){edges.push({from:from.id,to:to.id,type:edge[1],label:edge[2]||''});seen.add(key);}
   lastEnd=to.end;i=to.end;
  }
  if(!edges.length)return null;
  return {direction:direction[1].toUpperCase(),nodes:[...nodes.values()],edges,consumed:lastEnd,raw:input.slice(0,lastEnd)};
 }
 function extract(input,push){
  // Markdown code, prose, and inline examples must never be interpreted as DIL.
  // Literal delimiters in a saved JSON attribute or copyable block are data,
  // rather than markdown delimiters. Skip intact components before splitting.
  const parts=[],components=new Map();let begin=0,cursor=0;
  while(cursor<input.length){
   if(input[cursor]==='<'){
    const tag=readTag(input,cursor),component=tag&&!tag.close&&ROOT.test(tag.name)?layout(input,cursor):null;
    if(component){components.set(cursor,component);cursor=component.end;continue;}if(tag){cursor=tag.end;continue;}
   }
   const delimiter=input.slice(cursor).match(/^(?:`{3,}|~{3,}|`)/)?.[0];
   if(delimiter){const finish=input.indexOf(delimiter,cursor+delimiter.length),end=finish<0?input.length:finish+delimiter.length;
    if(delimiter.length>=3||finish>=0&&!input.slice(cursor,end).includes('\n')){parts.push(input.slice(begin,cursor),input.slice(cursor,end));cursor=end;begin=end;continue;}}
   cursor++;
  }
  parts.push(input.slice(begin));
  let partOffset=0;
  return parts.map((part,i)=>{
   const base=partOffset;partOffset+=part.length;
   if(i%2){
    const fenced=part.match(/^(?:`{3,}|~{3,})\s*mermaid\s*\r?\n([\s\S]*?)(?:\r?\n(?:`{3,}|~{3,})\s*)?$/i);
    if(fenced){const value=graph(fenced[1].trim());if(value)return '\n'+push({diagram:value})+'\n';}
    return part;
   }
   let result='',pos=0;
   const start=/<Chart\b|<(?:grid|flow|row|col|box|card|table|data-table|progress(?:-bar)?|meter|bar|bars|comparison|copy|copyable|code-block|button|tabs|accordion|details|columns|column|newspaper|section|article|panel|stack|status|status-badge)\b|(?:^|\n)[ \t]*(?:flowchart|graph)\s+(?:TD|TB|BT|LR|RL)\b/gim;
   let m;while((m=start.exec(part))){
    const at=part[m.index]==='\n'?m.index+1:m.index;
    if(at<pos)continue;
    const kind=part[at]==='<'?'jsx':'diagram';
    const memo=components.get(base+at);
    const value=kind==='diagram'?graph(part.slice(at).trimStart()):part.slice(at,at+7).toLowerCase().startsWith('<chart')?chart(part,at):memo?{...memo,end:memo.end-base}:layout(part,at);
   if(!value){
    // Retain malformed saved components as inert source. Do not independently
    // render fragments inside a broken parent or discard them as HTML tags.
    const tag=kind==='jsx'?readTag(part,at):null;
    if(!tag){if(kind!=='jsx')continue;const separator=part.indexOf('\n\n',at),end=separator<0?part.length:separator;result+=part.slice(pos,at)+'\n'+push({unavailable:{title:'Incomplete saved content',raw:part.slice(at,end)}})+'\n';pos=end;start.lastIndex=pos;continue;}
    const close=new RegExp('</\\s*'+tag.name+'\\s*>','ig');close.lastIndex=tag.end;
    const ending=tag.self?null:close.exec(part);const end=tag.self?tag.end:ending?ending.index+ending[0].length:Math.min(part.length,at+260000);
    result+=part.slice(pos,at)+'\n'+push({unavailable:{title:'Saved content preview unavailable',raw:part.slice(at,end)}})+'\n';pos=end;start.lastIndex=pos;continue;
   }
    result+=part.slice(pos,at);
    result+='\n'+push(kind==='diagram'?{diagram:value}:value.value.chartType?{chart:value.value}:{layout:value.value,source:value.raw})+'\n';
    pos=kind==='diagram'?at+part.slice(at).length-part.slice(at).trimStart().length+value.consumed:value.end;
    start.lastIndex=pos;
   }
   return result+part.slice(pos);
  }).join('');
 }
 function splitLines(value,width=28){const text=String(value||'').trim(),lines=[];
  for(const paragraph of text.split('\n')){
   let current='';for(const word of paragraph.split(/\s+/)){
    if(current&&current.length+word.length+1>width){lines.push(current);current='';}
    if(word.length>width){if(current){lines.push(current);current='';}for(let p=0;p<word.length;p+=width)lines.push(word.slice(p,p+width));}
    else current+=(current?' ':'')+word;
   }
   if(current)lines.push(current);
  }
  return lines.slice(0,12);
 }
 function diagramModel(spec){
  // Dagre handles arbitrary DAGs and cyclic/feedback links without placing
  // connector splines through intermediate nodes. Bundled offline and pinned.
  const engine=window.dagre;
  if(!engine?.graphlib?.Graph)throw Error('The bundled flowchart layout engine is unavailable');
  const graph=new engine.graphlib.Graph({multigraph:true});
  graph.setGraph({rankdir:spec.direction==='TD'?'TB':spec.direction,ranksep:82,nodesep:56,edgesep:24,marginx:38,marginy:35,acyclicer:'greedy'});
  graph.setDefaultEdgeLabel(()=>({}));
  const position=new Map();
  for(const item of spec.nodes){
   const lines=splitLines(item.label,36),width=Math.max(204,Math.min(346,Math.max(...lines.map(line=>line.length),12)*7.5+40)),height=Math.max(66,lines.length*20+30);
   graph.setNode(item.id,{width,height,lines});
  }
  for(let i=0;i<spec.edges.length;i++){
   const edge=spec.edges[i];graph.setEdge(edge.from,edge.to,{weight:2,minlen:1},'edge'+i);
  }
  engine.layout(graph);
  for(const item of spec.nodes){
   const value=graph.node(item.id);
   position.set(item.id,{x:value.x-value.width/2,y:value.y-value.height/2,width:value.width,height:value.height,lines:value.lines});
  }
  const links=spec.edges.map((edge,i)=>({...edge,points:graph.edge({v:edge.from,w:edge.to,name:'edge'+i})?.points||[]}));
  const horizontal=['LR','RL'].includes(spec.direction),groups=new Map();
  for(const item of spec.nodes){const value=graph.node(item.id),rank=Math.round((horizontal?value.x:value.y)/25)*25;if(!groups.has(rank))groups.set(rank,[]);groups.get(rank).push(item.id);}
  return {position,width:graph.graph().width,height:graph.graph().height,tiers:[...groups.entries()].sort((a,b)=>a[0]-b[0]).map(x=>x[1]),links};
 }
 function diagram(spec,sourceFn){
  const card=n('section','saved-widget rich-diagram'),bar=n('div','rich-diagram-toolbar'),name=n('strong','','Flowchart'),expand=n('button','rich-diagram-expand','Expand ↗'),viewport=n('div','rich-diagram-viewport');
  const model=diagramModel(spec);
  name.textContent='Flowchart · '+spec.nodes.length+' nodes';bar.append(name,expand);card.append(bar,viewport);
  const drawing=svg('svg',{viewBox:`0 0 ${model.width} ${model.height}`,role:'img','aria-label':'Saved flowchart, '+spec.nodes.length+' nodes and '+spec.edges.length+' connections'});
  drawing.style.width='min(100%, '+model.width+'px)';const defs=svg('defs'),marker=svg('marker',{id:'viewer-graph-arrow-'+Math.random().toString(36).slice(2),markerWidth:8,markerHeight:8,refX:6,refY:3,orient:'auto',markerUnits:'strokeWidth'});
  marker.append(svg('path',{d:'M 0 0 L 6 3 L 0 6 z',fill:'var(--muted)'}));defs.append(marker);drawing.append(defs);
  for(const edge of model.links){
   const points=edge.points;if(points.length<2)continue;
   // The engine returns correctly routed endpoints and bend points. Rounding
   // corners, rather than inventing Bezier control handles, avoids loopbacks.
   let d='M '+points[0].x+' '+points[0].y;
   for(let i=1;i<points.length-1;i++){
    const p=points[i],next=points[i+1],mid={x:(p.x+next.x)/2,y:(p.y+next.y)/2};
    d+=' Q '+p.x+' '+p.y+' '+mid.x+' '+mid.y;
   }
   d+=' L '+points.at(-1).x+' '+points.at(-1).y;
   const p=svg('path',{d,fill:'none',stroke:'var(--muted)','stroke-width':1.5,'stroke-linecap':'round','marker-end':'url(#'+marker.getAttribute('id')+')'});
   if(edge.type==='-.->')p.setAttribute('stroke-dasharray','5 5');if(edge.type==='==>')p.setAttribute('stroke-width','2.8');
   p.append(svg('title',{},edge.from+' → '+edge.to+(edge.label?' · '+edge.label:'')));drawing.append(p);
  }
  for(const {id,label} of spec.nodes){const p=model.position.get(id);if(!p)continue;
   const group=svg('g',{class:'rich-diagram-node'}),rect=svg('rect',{x:p.x,y:p.y,width:p.width,height:p.height,rx:16,fill:'#052d50',stroke:'#195077','stroke-width':1.3});
   group.append(rect);const lines=p.lines;
   const text=svg('text',{x:p.x+p.width/2,y:p.y+p.height/2-(lines.length-1)*10,'text-anchor':'middle',fill:'#a7d3fa','font-size':14,'font-weight':600});
   lines.forEach((line,i)=>text.append(svg('tspan',{x:p.x+p.width/2,dy:i===0?0:20},line)));
   group.append(text,svg('title',{},label));drawing.append(group);
  }
  viewport.append(drawing);
  expand.onclick=()=>{
   // showModal enters the top layer. Fixed positioning inside a
   // content-visibility:auto message is clipped by its containment box.
   const modal=n('dialog','rich-diagram-modal'),toolbar=n('div','rich-diagram-modal-toolbar'),label=n('strong','','Flowchart · '+spec.nodes.length+' nodes'),controls=n('div','rich-diagram-zoom-controls');
   const out=n('button','','−'),fit=n('button','','Fit'),reset=n('button','','100%'),zoomIn=n('button','','+'),close=n('button','','Close ×');
   [out,fit,reset,zoomIn,close].forEach(button=>controls.append(button));
   toolbar.append(label,controls);modal.append(toolbar,viewport);document.body.append(modal);
   let scale=1;
   const apply=value=>{scale=Math.max(.25,Math.min(3,value));drawing.style.width=Math.round(model.width*scale)+'px';drawing.style.minWidth='0';reset.textContent=Math.round(scale*100)+'%';};
   const fitView=()=>apply(Math.min((viewport.clientWidth-25)/model.width,(viewport.clientHeight-25)/model.height,1.5));
   out.onclick=()=>apply(scale/1.25);zoomIn.onclick=()=>apply(scale*1.25);fit.onclick=fitView;reset.onclick=()=>apply(1);close.onclick=()=>modal.close();
   modal.addEventListener('close',()=>{card.insertBefore(viewport,card.querySelector('.widget-source'));drawing.style.width='min(100%, '+model.width+'px)';drawing.style.minWidth='0';modal.remove();expand.focus({preventScroll:true});},{once:true});
   modal.showModal();fitView();
  };
  if(sourceFn)sourceFn(card,spec.raw,'mermaid','Diagram source');
  return card;
 }
 function layoutRender(spec,sourceFn,raw,context={}){
  const card=n('section','saved-widget rich-dil-layout');
  const link=(label,address)=>{
   const a=n('a','rich-dil-file-link',label);
   if(/^https?:\/\//i.test(address)){
    try{const url=new URL(address);if(/^https?:$/.test(url.protocol)){a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';return a;}}catch{}
   }
   // sandbox:/mnt/data is an identifier in an exported ChatGPT answer, NOT
   // a filesystem path the offline viewer can resolve or open directly.
   // Search only real attachments indexed to the current conversation.
   const file=/^sandbox:\/mnt\/data\/([^?#]+)$/i.exec(address);
   if(file){
    const name=decodeURIComponent(file[1].split('/').at(-1));
    a.href='#';a.title='Open the matching locally saved attachment, if available';
    a.onclick=async event=>{
     event.preventDefault();
     try{
      if(context.cid&&window.ThreadAttachments?.catalog){
       const found=await window.ThreadAttachments.catalog(context.cid,window.S?.leaf);
       const attachment=(found.attachments||[]).find(f=>f.available&&String(f.name||'').toLowerCase()===name.toLowerCase());
       if(attachment){await window.ThreadAttachments.open(context.cid,attachment.id,null,window.S?.leaf);return;}
      }
      window.toast?.('This spreadsheet was linked in the original ChatGPT response but was not saved in this offline export.');
     }catch(error){window.toast?.(error.message||'Attachment unavailable');}
    };
   }else{a.removeAttribute('href');a.title='Original link was not retained in this export';}
   return a;
  };
  function inline(host,text){
   const re=/(\*\*)?\[([^\]]+)\]\(((?:[^()]|\([^()]*\))*)\)(\*\*)?|\*\*([^*]+)\*\*|\[(OK|PASS|SUCCESS|WARN|WARNING|ERROR|FAIL|FAILED|PENDING|INFO)\]/gi;
   let start=0;
   for(const match of text.matchAll(re)){
    if(match.index>start)host.append(document.createTextNode(text.slice(start,match.index)));
    if(match[2])host.append(link(match[2],match[3]));
    else if(match[6])host.append(status(match[0],match[6]));
    else host.append(n('strong','',match[5]));
    start=match.index+match[0].length;
   }
   if(start<text.length)host.append(document.createTextNode(text.slice(start)));
  }
  const textOf=item=>typeof item==='string'?item:(item.children||[]).map(textOf).join('')||String(attr(item.attrs||{},'label','text','value')??'');
  const attr=(a,...keys)=>keys.map(k=>a[k]).find(v=>v!==undefined);
  const numeric=value=>value!==undefined&&value!==null&&String(value).trim()!==''&&Number.isFinite(Number(value))?Number(value):null;
  const palette={pink:'#b68aa5',blue:'var(--accent)',green:'#59b56b',orange:'#ee8b43',purple:'#bd84ea',red:'#ed6e8a',teal:'#48babe',accent:'var(--accent)'};
  function status(label,state=''){
   const normalized=String(state||label).replace(/[\[\]]/g,'').toLowerCase(),tone=/^(ok|pass|success|complete|ready|green)$/.test(normalized)?'ok':/^(warn|warning|pending|yellow|orange)$/.test(normalized)?'warn':/^(error|fail|failed|red)$/.test(normalized)?'error':'info';
   return n('span','rich-dil-status rich-dil-status-'+tone,label);
  }
  function dimensions(value){
   if(value===undefined)return null;
   const match=String(value).match(/^(\d+(?:\.\d+)?)(px|%|rem|em)?$/);if(!match)return null;
   const unit=match[2]||'px',amount=Math.min(unit==='%'?100:unit==='px'?4096:128,Number(match[1])*(match[2]?1:4));return amount+unit;
  }
  function appearance(node,item){
   const a=item.attrs||{},size=dimensions(a.width),height=dimensions(a.height);
   if(size){node.style.width=size;node.style.maxWidth='100%';}if(height){node.style.height=height;node.style.minHeight='0';if(!item.children?.length){node.style.padding='0';node.style.border='0';}}
   for(const prop of ['gap','padding'])if(a[prop]!==undefined){const amount=numeric(a[prop]);if(amount!==null&&amount>=0)node.style[prop]=Math.min(128,amount*4)+'px';}
   if(a.border==='false'||a.border==='0')node.style.border='0';
   if(a.radius!==undefined){const radius={none:'0',sm:'5px',md:'9px',lg:'13px',xl:'18px',full:'999px'}[a.radius]||dimensions(a.radius);if(radius)node.style.borderRadius=radius;}
   const color=String(a.background||'');if(palette[color]||/^#[0-9a-f]{3,8}$/i.test(color))node.style.background=palette[color]||color;else if(['panel','secondary','muted'].includes(color))node.style.background='var(--panel)';else if(['none','transparent'].includes(color))node.style.background='transparent';
   if(a.clip==='true')node.style.overflow='hidden';
   if(['start','end','center','stretch','baseline'].includes(a.align))node.style.alignItems=a.align;
   if(['start','end','center','space-between','space-around','space-evenly'].includes(a.justify))node.style.justifyContent=a.justify;
   const flex=numeric(a.flex);if(flex!==null&&flex>=0&&flex<=100)node.style.flex=flex+' 1 0%';
  }
  function bar(item){
   const a=item.attrs||{},row=n('div','rich-dil-meter-row'),heading=n('div','rich-dil-meter-heading'),label=attr(a,'label','title','name')||textOf(item).trim(),value=numeric(attr(a,'value','percent','percentage')),min=numeric(a.min)??0,max=numeric(a.max)??100;
   const valueLabel=attr(a,'valuelabel','value-label','valuetext','value-text','description','status');
   heading.append(n('strong','rich-dil-meter-label',label),n('span','rich-dil-meter-value',valueLabel??(value===null?String(attr(a,'value','percent','percentage')??''):String(value)+(a.unit||''))));row.append(heading);
   if(value!==null&&max>min){
    const track=n('div','rich-dil-meter-track'),fill=n('span','rich-dil-meter-fill');
    fill.style.width=Math.max(0,Math.min(100,(value-min)/(max-min)*100))+'%';
    const color=String(a.color||a.fill||'accent');if(palette[color]||/^#[0-9a-f]{3,8}$/i.test(color))fill.style.background=palette[color]||color;
    track.setAttribute('role',item.type==='progress'||item.type==='progress-bar'?'progressbar':'meter');track.setAttribute('aria-label',label||'Saved value');track.setAttribute('aria-valuemin',min);track.setAttribute('aria-valuemax',max);track.setAttribute('aria-valuenow',Math.max(min,Math.min(max,value)));if(valueLabel)track.setAttribute('aria-valuetext',valueLabel);track.append(fill);row.append(track);
   }
   if(a.caption)row.append(n('small','rich-dil-subtext',a.caption));return row;
  }
  async function copy(button,value){
   if(button.dataset.busy)return;button.dataset.busy='1';
   try{await navigator.clipboard.writeText(String(value));window.toast?.('Copied');}
   catch{window.toast?.('Copy unavailable. Select the text and copy it manually.');}
   finally{delete button.dataset.busy;}
  }
  function copyable(item){
   const a=item.attrs||{},value=attr(a,'text','value','content')??textOf(item),wrap=n('div','rich-dil-copyable'),top=n('div','rich-dil-control-heading'),button=n('button','rich-dil-control','Copy'),pre=n('pre'),code=n('code','',value);
   button.type='button';button.setAttribute('aria-label','Copy '+(a.label||a.title||'saved text'));button.onclick=()=>copy(button,value);top.append(n('strong','',a.label||a.title||'Saved text'),button);pre.append(code);wrap.append(top,pre);return wrap;
  }
  function disclosure(item){
   const a=item.attrs||{},details=n('details','rich-dil-disclosure'),heading=(item.children||[]).find(c=>typeof c==='object'&&c.type==='summary');details.open=a.open==='true';details.append(n('summary','',a.title||a.label||(heading?textOf(heading):'Details')));
   const body=n('div','rich-dil-disclosure-body');for(const c of item.children||[]){if(c===heading)continue;const v=child(c);if(v)body.append(v);}details.append(body);return details;
  }
  function tabs(item){
   const a=item.attrs||{},wrap=n('div','rich-dil-tabs'),list=n('div','rich-dil-tab-list'),panels=n('div','rich-dil-tab-panels'),entries=(item.children||[]).filter(c=>typeof c==='object'&&['tab','tab-panel'].includes(c.type));
   if(!entries.length){for(const c of item.children||[]){const v=child(c);if(v)wrap.append(v);}return wrap;}
   list.setAttribute('role','tablist');list.setAttribute('aria-label',a.label||a.title||'Saved content');const buttons=[],bodies=[],id='saved-tabs-'+crypto.randomUUID();
   const activate=(i,focus=false)=>{buttons.forEach((b,k)=>{b.setAttribute('aria-selected',String(k===i));b.tabIndex=k===i?0:-1;bodies[k].hidden=k!==i;});if(focus)buttons[i].focus();};
   entries.forEach((entry,i)=>{const button=n('button','rich-dil-tab',entry.attrs?.title||entry.attrs?.label||'Tab '+(i+1)),body=n('div','rich-dil-tab-panel');button.type='button';button.id=id+'-tab-'+i;body.id=id+'-panel-'+i;button.setAttribute('role','tab');button.setAttribute('aria-controls',body.id);body.setAttribute('role','tabpanel');body.setAttribute('aria-labelledby',button.id);body.tabIndex=0;button.onclick=()=>activate(i);button.onkeydown=event=>{let target=i;if(event.key==='ArrowRight')target=(i+1)%entries.length;else if(event.key==='ArrowLeft')target=(i+entries.length-1)%entries.length;else if(event.key==='Home')target=0;else if(event.key==='End')target=entries.length-1;else return;event.preventDefault();activate(target,true);};for(const c of entry.children||[]){const v=child(c);if(v)body.append(v);}buttons.push(button);bodies.push(body);list.append(button);panels.append(body);});
   wrap.append(list,panels);let selected=entries.findIndex(e=>a.value!==undefined&&e.attrs?.value===a.value||a.selected!==undefined&&e.attrs?.id===a.selected);if(selected<0)selected=Math.max(0,Math.min(entries.length-1,numeric(a.selected)??0));activate(selected);return wrap;
  }
  function table(item){
   const a=item.attrs||{},spec=a.content&&typeof a.content==='object'?a.content:null,rows=[],labels=[];
   const plain=value=>value===null||value===undefined?'':typeof value==='object'?JSON.stringify(value):String(value);
   if(spec){
    const data=Array.isArray(spec.rows)?spec.rows:Array.isArray(spec.data)?spec.data:[],columns=Array.isArray(spec.columns)?spec.columns:Object.keys(data[0]||{});
    for(const col of columns)labels.push(typeof col==='string'?col:String(col.label||col.title||col.key||col.dataKey||''));
    data.slice(0,100000).forEach((row,index)=>rows.push({index,cells:columns.map((col,i)=>plain(Array.isArray(row)?row[i]:row?.[typeof col==='string'?col:col.key||col.dataKey||col.field])),rich:null}));
   }else{
    function collect(node,header=false){
     if(typeof node==='string')return;
     const isHeader=header||node.attrs?.header==='true'||['table-head','thead'].includes(node.type);
     if(['table-row','tr'].includes(node.type)){
      const cells=(node.children||[]).filter(c=>typeof c==='object'&&['table-cell','td','th'].includes(c.type));
      if(isHeader||cells.length&&cells.every(c=>c.attrs?.header==='true'||c.type==='th')){if(!labels.length)labels.push(...cells.map(textOf));}
      else rows.push({index:rows.length,cells:cells.map(textOf),rich:cells});
     }else for(const c of node.children||[])collect(c,isHeader);
    }
    collect(item);if(!labels.length){const width=Math.max(0,...rows.map(r=>r.cells.length));for(let i=0;i<width;i++)labels.push('Column '+(i+1));}
   }
   const totalColumns=labels.length;if(totalColumns>64){labels.length=64;for(const row of rows){row.cells=row.cells.slice(0,64);if(row.rich)row.rich=row.rich.slice(0,64);}}
   const wrap=n('section','rich-dil-data-table'),toolbar=n('div','rich-dil-table-toolbar'),count=n('span','rich-dil-table-count'),filter=n('input','rich-dil-table-filter'),copyButton=n('button','rich-dil-control','Copy'),viewport=n('div','rich-dil-table-viewport'),table=n('table','rich-dil-table'),head=n('thead'),header=n('tr'),body=n('tbody'),footer=n('div','rich-dil-table-pages'),previous=n('button','rich-dil-control','Previous'),next=n('button','rich-dil-control','Next');
   filter.type='search';filter.placeholder='Filter rows';filter.setAttribute('aria-label','Filter '+(a.title||'saved table'));copyButton.type=previous.type=next.type='button';copyButton.title='Copy all matching rows as tab-separated text';viewport.tabIndex=0;viewport.setAttribute('aria-label',a.title||'Scrollable saved table');
   const collator=new Intl.Collator(undefined,{numeric:true,sensitivity:'base'}),search=rows.map(r=>r.cells.join(' ').normalize('NFKC').toLowerCase());let matching=rows.slice(),sortKey=-1,direction=0,page=0;
   function draw(){
    body.replaceChildren();const start=page*100;
    for(const row of matching.slice(start,start+100)){const tr=n('tr');for(let i=0;i<labels.length;i++){const cell=n('td');if(row.rich?.[i]){for(const c of row.rich[i].children||[]){const v=child(c);if(v)cell.append(v);}}else inline(cell,row.cells[i]||'');tr.append(cell);}body.append(tr);}
    count.textContent=matching.length?(start+1)+'–'+Math.min(start+100,matching.length)+' of '+matching.length+' rows':'0 rows';previous.disabled=page===0;next.disabled=start+100>=matching.length;footer.hidden=matching.length<=100;
   }
   function update(){
    const query=filter.value.normalize('NFKC').toLowerCase();matching=rows.filter(r=>!query||search[r.index].includes(query));
    if(direction)matching.sort((a,b)=>{const av=a.cells[sortKey]||'',bv=b.cells[sortKey]||'',an=numeric(av),bn=numeric(bv);return direction*(an!==null&&bn!==null?an-bn:collator.compare(av,bv))||a.index-b.index;});page=0;draw();
   }
   labels.forEach((label,i)=>{const cell=n('th'),button=n('button','rich-dil-sort',label);button.type='button';button.title='Sort by '+label;button.onclick=()=>{direction=sortKey===i?(direction===1?-1:direction===-1?0:1):1;sortKey=i;for(const h of header.children)h.removeAttribute('aria-sort');cell.setAttribute('aria-sort',direction===1?'ascending':direction===-1?'descending':'none');update();};cell.append(button);header.append(cell);});
   filter.value='';filter.oninput=update;copyButton.onclick=()=>copy(copyButton,[labels,...matching.map(r=>r.cells)].map(row=>row.map(v=>String(v).replace(/[\t\r\n]+/g,' ')).join('\t')).join('\n'));previous.onclick=()=>{page--;draw();};next.onclick=()=>{page++;draw();};
   head.append(header);table.append(head,body);viewport.append(table);toolbar.append(n('strong','',a.title||spec?.title||'Saved table'),count,filter,copyButton);footer.append(previous,next);wrap.append(toolbar);
   for(const c of item.children||[])if(typeof c==='string'||!['table-row','tr','table-section','table-head','table-body','table-footer','thead','tbody','tfoot'].includes(c.type)){const extra=child(c);if(extra)wrap.append(extra);}
   wrap.append(viewport,footer);if(totalColumns>64)wrap.append(n('small','rich-dil-subtext','First 64 columns shown. The complete table is retained in Layout source.'));draw();return wrap;
  }
  function child(item){
   if(typeof item==='string'){
    const text=item.replace(/\s*\r?\n\s*/g,' ').trim();
    if(!text)return null;
    const span=n('span','rich-dil-literal');inline(span,text);return span;
   }
   const type=item.type,a=item.attrs||{};
    if(['table','data-table'].includes(type))return table(item);
    if(['status','status-badge'].includes(type))return status(a.label||textOf(item)||a.state||a.value||'',a.state||a.type||a.color||'');
    if(type==='icon'){const icon=n('span','rich-dil-icon',a.symbol||textOf(item)||{check:'✓',ok:'✓',warning:'⚠',error:'✕',info:'ⓘ'}[a.name]||a.name||'');if(a.label)icon.setAttribute('aria-label',a.label);if(palette[a.color])icon.style.color=palette[a.color];return icon;}
    if(type==='chart'&&item.chart)return window.SavedWidgets.render({chart:item.chart},context);
    if(['progress','progress-bar','meter','bar'].includes(type))return bar(item);
    if(['copy','copyable','code-block'].includes(type))return copyable(item);
    if(['accordion','details'].includes(type))return disclosure(item);
    if(type==='tabs')return tabs(item);
    if(type==='button'){
     const label=textOf(item).trim()||a.label||a.title||'Saved action';
     if(a.action==='copy'||a.copy!==undefined){const button=n('button','rich-dil-control',label);button.type='button';button.onclick=()=>copy(button,attr(a,'copy','value','text','content')??textOf(item));return button;}
     if(a.url||a.href)return link(label,a.url||a.href);
     const button=n('button','rich-dil-control',label);button.type='button';button.disabled=true;button.title='This action requires the original application';return button;
    }
   if(type==='link')return link(a.title||a.label||a.url||'Saved link',a.url||a.href||'');
    const node=n(type==='table-row'?'tr':type==='table-cell'?'td':type==='table-section'?'tbody':type==='title'?'strong':type==='heading'?'h3':type==='paragraph'?'p':type==='article'?'article':type==='section'?'section':type==='code'?'code':type==='caption'?'small':type==='divider'?'hr':type==='bold'||type==='strong'?'strong':type==='text'||type==='badge'?'span':'div','rich-dil-'+type);
    appearance(node,item);
    if(['grid','flow','columns','newspaper'].includes(type)){const cols=Number(a.columns)||Number(a.cols)||0;node.style.setProperty('--rich-dil-columns',String(Math.max(1,Math.min(8,cols||(['columns','newspaper'].includes(type)?2:3)))));}
   if(type==='table-row'&&a.header==='true'){node.dataset.header='true';}
   if(type==='table-cell'&&a.header==='true'){const head=n('th','rich-dil-table-cell');for(const c of item.children){const v=child(c);if(v)head.append(v);}return head;}
   if(type==='text'&&['xs','sm','small'].includes(a.size)||type==='caption')node.classList.add('rich-dil-subtext');
   if(type==='text'&&['secondary','muted','tertiary'].includes(a.color))node.classList.add('rich-dil-muted');
    if(['text','badge','label','value'].includes(type)&&(palette[a.color]||/^#[0-9a-f]{3,8}$/i.test(a.color||'')))node.style.color=palette[a.color]||a.color;
   if(type==='text'&&['lg','xl','2xl'].includes(a.size))node.classList.add('rich-dil-emphasis');
   if(type==='text'&&a.strong==='true'||type==='title')node.classList.add('rich-dil-strong');
   if(type==='badge'&&a.label)node.textContent=a.label;
    if(['text','title','heading','paragraph','label','value','code'].includes(type)&&!item.children?.length)node.textContent=String(attr(a,'text','label','value')??'');
   if(type==='table'&&a.dividers)node.classList.add('rich-dil-bordered');
    if(!TAGS.has(type)){node.classList.add('rich-dil-unknown');if(!item.children?.length)node.textContent=String(attr(a,'label','title','text','value')||'Saved '+type+' content');}
   for(const c of item.children||[]){const v=child(c);if(v)node.append(v);}
   return node;
  }
  card.append(child(spec));if(sourceFn)sourceFn(card,raw,'jsx','Layout source');return card;
 }
 return {extract,chart,graph,layout,diagramModel,diagram,layoutRender};
})();
