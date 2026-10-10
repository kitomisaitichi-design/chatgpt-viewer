'use strict';
// Render saved ChatGPT declarative content without evaluating exported JSX.
// The parser is data-driven: neither node labels nor chart values are templates.
window.StructuredContent=(()=>{
 const NODE=/^[A-Za-z_][\w.-]*/;
 const DIRECTION=/^(?:flowchart|graph)\s+(TD|TB|BT|LR|RL)\b/i;
 const ROOT=/^(?:grid|flow|row|col|box|card|table)$/i;
 const TAGS=new Set(['grid','grid-item','flow','flow-item','row','col','box','card','text','title','caption','bold','strong','small','badge','divider','spacer','table','table-section','table-row','table-cell','link']);
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
  const values={};
  for(const m of tag.matchAll(/([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|\{([^{}]*)\})/g))values[m[1].toLowerCase()]=m[2]??m[3]??m[4];
  return values;
 }
 function layout(input,at){
  const first=readTag(input,at);if(!first||first.close||!ROOT.test(first.name))return null;
  const root={type:first.name,attrs:attrs(first.raw),children:[]},stack=[root];let pos=first.end;
  for(let count=0;pos<input.length&&count<8000;count++){
   const start=input.indexOf('<',pos);
   if(start<0)return null;
   if(start>pos)stack.at(-1).children.push(input.slice(pos,start));
   const tag=readTag(input,start);
   if(!tag||!TAGS.has(tag.name))return null;
   if(tag.close){
    if(stack.at(-1).type!==tag.name)return null;
    stack.pop();pos=tag.end;
    if(!stack.length)return {value:root,end:pos,raw:input.slice(at,pos)};
   }else{
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
  const parts=input.split(/(`{3,}[\s\S]*?(?:`{3,}|$)|~{3,}[\s\S]*?(?:~{3,}|$)|`[^`\n]*`)/g);
  return parts.map((part,i)=>{
   if(i%2){
    const fenced=part.match(/^(?:`{3,}|~{3,})\s*mermaid\s*\r?\n([\s\S]*?)(?:\r?\n(?:`{3,}|~{3,})\s*)?$/i);
    if(fenced){const value=graph(fenced[1].trim());if(value)return '\n'+push({diagram:value})+'\n';}
    return part;
   }
   let result='',pos=0;
   const start=/<Chart\b|<(?:grid|flow|row|col|box|card|table)\b|(?:^|\n)[ \t]*(?:flowchart|graph)\s+(?:TD|TB|BT|LR|RL)\b/gim;
   let m;while((m=start.exec(part))){
    const at=part[m.index]==='\n'?m.index+1:m.index;
    if(at<pos)continue;
    const kind=part[at]==='<'?'jsx':'diagram';
    const value=kind==='diagram'?graph(part.slice(at).trimStart()):part.slice(at,at+7).toLowerCase().startsWith('<chart')?chart(part,at):layout(part,at);
    if(!value)continue;
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
   const re=/(\*\*)?\[([^\]]+)\]\(((?:[^()]|\([^()]*\))*)\)(\*\*)?|\*\*([^*]+)\*\*/g;
   let start=0;
   for(const match of text.matchAll(re)){
    if(match.index>start)host.append(document.createTextNode(text.slice(start,match.index)));
    if(match[2])host.append(link(match[2],match[3]));
    else host.append(n('strong','',match[5]));
    start=match.index+match[0].length;
   }
   if(start<text.length)host.append(document.createTextNode(text.slice(start)));
  }
  function child(item){
   if(typeof item==='string'){
    const text=item.replace(/\s*\r?\n\s*/g,' ').trim();
    if(!text)return null;
    const span=n('span','rich-dil-literal');inline(span,text);return span;
   }
   const type=item.type,a=item.attrs||{};
   if(type==='link')return link(a.title||a.label||a.url||'Saved link',a.url||a.href||'');
   const node=n(type==='table'?'table':type==='table-row'?'tr':type==='table-cell'?'td':type==='table-section'?'tbody':type==='title'?'strong':type==='caption'?'small':type==='divider'?'hr':type==='bold'||type==='strong'?'strong':type==='text'||type==='badge'?'span':'div','rich-dil-'+type);
   if(type==='grid'||type==='flow'){const cols=Number(a.columns)||Number(a.cols)||0;node.style.setProperty('--rich-dil-columns',String(Math.max(1,Math.min(8,cols||3))));}
   if(type==='table-row'&&a.header==='true'){node.dataset.header='true';}
   if(type==='table-cell'&&a.header==='true'){const head=n('th','rich-dil-table-cell');for(const c of item.children){const v=child(c);if(v)head.append(v);}return head;}
   if(type==='text'&&['xs','sm','small'].includes(a.size)||type==='caption')node.classList.add('rich-dil-subtext');
   if(type==='text'&&['secondary','muted','tertiary'].includes(a.color))node.classList.add('rich-dil-muted');
   if(type==='text'&&['lg','xl','2xl'].includes(a.size))node.classList.add('rich-dil-emphasis');
   if(type==='text'&&a.strong==='true'||type==='title')node.classList.add('rich-dil-strong');
   if(type==='badge'&&a.label)node.textContent=a.label;
   if(type==='table'&&a.dividers)node.classList.add('rich-dil-bordered');
   for(const c of item.children||[]){const v=child(c);if(v)node.append(v);}
   return node;
  }
  card.append(child(spec));if(sourceFn)sourceFn(card,raw,'jsx','Layout source');return card;
 }
 return {extract,chart,graph,layout,diagramModel,diagram,layoutRender};
})();
