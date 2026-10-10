'use strict';
// Saved data becomes DOM nodes. Saved applications run only in an opaque,
// network-disabled sandbox; they never share the viewer's origin or cookies.
window.SavedWidgets=(()=>{
 const n=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;};
 const colors=['#5297ee','#59b56b','#ee8b43','#bd84ea','#ed6e8a','#48babe'],frames=new Map();
 window.addEventListener('message',event=>{const frame=frames.get(event.data?.viewerFrame);if(!frame)return;if(!frame.isConnected){frames.delete(event.data.viewerFrame);return;}if(event.source!==frame.contentWindow)return;const height=Number(event.data.height);if(Number.isFinite(height))frame.style.height=Math.max(320,Math.min(5000,height+36))+'px';});
 const svgNode=(tag,attrs,text)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs||{}))e.setAttribute(key,String(value));if(text!==undefined)e.textContent=String(text);return e;};
 function extract(text){text=window.RichMedia.blocks(text);const widgets=[];text=text.replace(/\ue200(genui|image_group)\ue202([\s\S]*?)\ue201/g,(raw,type,json,offset)=>{
  // Literal examples inside fenced code remain literal examples.
  let fence='';for(const line of text.slice(0,offset).split('\n')){const m=line.match(/^\s*(`{3,}|~{3,})/);if(m){if(!fence)fence=m[1][0];else if(fence===m[1][0])fence='';}}if(fence)return raw;
  try{const spec=JSON.parse(json),w=type==='image_group'?{image_group:spec}:spec;if(w.citation)return raw;return 'OFFLINEWIDGETPLACEHOLDER'+(widgets.push(w)-1)+'END';}
  catch{return 'OFFLINEWIDGETPLACEHOLDER'+(widgets.push({unavailable:{title:'Incomplete saved widget',raw}})-1)+'END';}
 });
 // A long message may arrive in fragments. Do not show half a JSON document.
 const partial=text.indexOf('\ue200genui\ue202');if(partial>=0&&!text.includes('\ue201',partial)){text=text.slice(0,partial)+'OFFLINEWIDGETPLACEHOLDER'+(widgets.push({unavailable:{title:'Loading saved widget…'}})-1)+'END';}
  text=window.StructuredContent.extract(text,value=>'OFFLINEWIDGETPLACEHOLDER'+(widgets.push(value)-1)+'END');
  // ChatGPT often serializes a single download collection as consecutive
  // <box> components. Reassemble the collection instead of giving every
  // downloaded-item row its own border and a separate source-code panel.
  const isDownload=item=>item?.layout?.type==='box'&&/\[[^\]]+\]\((?:sandbox:|https?:)/i.test(item.source||'');
  const pair=/OFFLINEWIDGETPLACEHOLDER(\d+)END\s+OFFLINEWIDGETPLACEHOLDER(\d+)END/g;
  let changed=true;
  while(changed){
   changed=false;
   text=text.replace(pair,(raw,a,b)=>{
    const left=widgets[+a],right=widgets[+b];
    if(!left||!right||!(isDownload(left)||Array.isArray(left.downloads))||!isDownload(right))return raw;
    changed=true;
    return 'OFFLINEWIDGETPLACEHOLDER'+(widgets.push({downloads:[...(left.downloads||[left]),right]})-1)+'END';
   });
  }
  return window.RichMedia.combine(text,widgets);}
 function source(card,value,language='json',label='Saved source'){
  const fold=n('details','widget-source'),summary=n('summary','',label),pre=n('pre'),code=n('code');code.className='language-'+language;code.dataset.language=language;code.textContent=typeof value==='string'?value:JSON.stringify(value,null,2);pre.append(code);fold.append(summary,pre);card.append(fold);return fold;
 }
 function number(value,series={}){if(value===null||value===undefined||value==='')return '—';const v=Number(value);if(!Number.isFinite(v))return String(value);return (series.valuePrefix||'')+new Intl.NumberFormat(undefined,{maximumFractionDigits:3,...(series.valueFormat==='compact'?{notation:'compact'}:{})}).format(v)+(series.valueSuffix||'');}
 function chart(spec){
  const card=n('section','saved-widget saved-chart'),meta=spec.meta||{},data=Array.isArray(spec.data)?spec.data:[],series=Array.isArray(spec.series)?spec.series.slice(0,16):[],type=String(spec.chartType||'line').toLowerCase();
  card.classList.add('native-chart');const heading=n('div','native-chart-heading'),title=n('h4','widget-title',meta.title||'Chart'),expand=n('button','native-chart-expand','Expand ↗');
  heading.append(title,expand);card.append(heading);if(meta.description)card.append(n('p','widget-description',meta.description));
  const legend=n('div','chart-legend'),plot=n('div','chart-plot'),tip=n('div','chart-tooltip');tip.hidden=true;plot.append(tip);card.append(plot,legend);const enabled=new Set(series.map((_,i)=>i)),seriesColor=i=>/^#[0-9a-f]{3,8}$/i.test(series[i]?.color||'')?series[i].color:colors[i%colors.length];
  function draw(){const old=plot.querySelector('svg');old?._cancelHover?.();old?.remove();tip.hidden=true;const horizontal=type==='bar'&&spec.layout==='vertical',W=900,H=horizontal?Math.max(320,Math.min(850,data.length*35+70)):400,R=25,T=24,B=horizontal?45:75;let L=horizontal?240:95;
   const svg=svgNode('svg',{viewBox:'0 0 '+W+' '+H,role:'img',tabindex:0,'aria-label':(meta.title||'Saved chart')+' · hover for values; use arrow keys to inspect points'});plot.prepend(svg);
   const shown=series.map((s,i)=>({s,i})).filter(x=>enabled.has(x.i));let minimum=Infinity,maximum=-Infinity;for(const row of data)for(const {s} of shown){const v=row?.[s.dataKey];if(ChartMath.finite(v)){minimum=Math.min(minimum,Number(v));maximum=Math.max(maximum,Number(v));}}
   if(!data.length||!shown.length||!Number.isFinite(minimum)||!['line','area','bar','scatter'].includes(type)){svg.append(svgNode('text',{x:W/2,y:80,'text-anchor':'middle'},!shown.length?'Select a series below':'See the saved data below'));return;}
   let lo=Math.min(0,minimum),hi=Math.max(0,maximum);if(Number.isFinite(Number(spec.yAxisMin))&&spec.yAxisMin!==undefined&&spec.yAxisMin!==null)lo=Number(spec.yAxisMin);if(Number.isFinite(Number(spec.yAxisMax))&&spec.yAxisMax!==undefined&&spec.yAxisMax!==null)hi=Number(spec.yAxisMax);if(lo>=hi){lo=Math.min(0,minimum);hi=Math.max(0,maximum);}if(lo===hi)hi=lo+1;const magnitude=10**Math.floor(Math.log10((hi-lo)/4)),step=Math.ceil((hi-lo)/4/magnitude)*magnitude;if(spec.yAxisMin===undefined)lo=Math.floor(lo/step)*step;if(spec.yAxisMax===undefined)hi=Math.ceil(hi/step)*step;
   const measure=n('canvas').getContext('2d');if(measure)measure.font='13px system-ui';const width=text=>measure?measure.measureText(text).width:String(text).length*7.5;
   const axisLabels=horizontal?data.map(row=>{const label=String(row[spec.xKey]??'');return label.length>31?label.slice(0,29)+'…':label;}):Array.from({length:5},(_,i)=>number(lo+(hi-lo)*i/4,shown[0].s));
   for(const label of axisLabels)L=Math.max(L,width(label)+24);L=Math.min(W*.48,L);const iw=W-L-R,ih=H-T-B;
   const y=v=>T+ih-(Number(v)-lo)/(hi-lo)*ih,xValue=v=>L+(Number(v)-lo)/(hi-lo)*iw;const sx=data.map(d=>ChartMath.finite(d[spec.xKey])?Number(d[spec.xKey]):NaN),xextent=ChartMath.extent(sx),xmin=Number.isFinite(xextent.min)?xextent.min:0,xmax=Number.isFinite(xextent.max)?xextent.max:1,numericX=spec.xAxisScale==='linear'&&['line','area'].includes(type)&&sx.every((v,i)=>Number.isFinite(v)&&(!i||v>=sx[i-1]))&&xmax>xmin;
   const x=(row,i)=>type==='scatter'||numericX?L+(Number(row[spec.xKey])-xmin)/(xmax-xmin||1)*iw:L+i/Math.max(1,data.length-1)*iw;
   for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4,at=horizontal?xValue(v):y(v);svg.append(svgNode('line',horizontal?{x1:at,y1:T,x2:at,y2:T+ih,class:'chart-grid'}:{x1:L,y1:at,x2:W-R,y2:at,class:'chart-grid'}));svg.append(svgNode('text',horizontal?{x:at,y:H-18,'text-anchor':'middle',class:'chart-tick'}:{x:L-10,y:at+4,'text-anchor':'end',class:'chart-tick'},number(v,shown[0].s)));}
   function tooltip(target,row,s){const title=svgNode('title',{},String(row[spec.xKey]??'')+' · '+(row.material||row.label||'')+' · '+(s.label||s.dataKey)+': '+number(row[s.dataKey],s));target.append(title);target.onpointerenter=()=>{tip.textContent=title.textContent;tip.hidden=false;};target.onpointerleave=()=>tip.hidden=true;}
   for(const {s,i:si} of shown){const color=seriesColor(si),group=svgNode('g',{'data-series':s.dataKey});svg.append(group);let path='',pen=false;
    const indices=ChartMath.samples(data,s.dataKey);let previous=-1;for(const i of indices){for(let k=previous+1;k<i;k++)if(!ChartMath.finite(data[k]?.[s.dataKey])){pen=false;break;}previous=i;const row=data[i],v=row?.[s.dataKey];if(v===null||v===undefined||v===''||!Number.isFinite(Number(v))){pen=false;continue;}const xx=x(row,i),yy=y(v);if(type==='line'||type==='area'){path+=(pen?'L':'M')+xx.toFixed(2)+' '+yy.toFixed(2)+' ';pen=true;}
     let mark;if(type==='bar'){const slot=(horizontal?ih:iw)/data.length,siIndex=shown.findIndex(item=>item.i===si),bw=slot*.78/shown.length;
      if(horizontal){const base=xValue(0),value=xValue(v);mark=svgNode('rect',{x:Math.min(base,value),y:T+i*slot+slot*.11+siIndex*bw,width:Math.max(1,Math.abs(value-base)),height:Math.max(1,bw-1),fill:color,rx:4,class:'chart-bar','data-point':i});}
      else{const base=y(0);mark=svgNode('rect',{x:L+i*slot+slot*.11+siIndex*bw,y:Math.min(base,yy),width:Math.max(1,bw-1),height:Math.max(1,Math.abs(base-yy)),fill:color,rx:4,class:'chart-bar','data-point':i});}
     }else if(type==='scatter'||data.length<=250)mark=svgNode('circle',{cx:xx,cy:yy,r:type==='scatter'?5:3.4,fill:color,stroke:'var(--bg)','stroke-width':1});if(mark){tooltip(mark,row,s);group.append(mark);}
    }
    if(path){const line=svgNode('path',{d:path.trim(),fill:'none',stroke:color,'stroke-width':2.2,'stroke-linejoin':'round'});group.prepend(line);}
   }
   const stride=Math.max(1,Math.ceil(data.length/(horizontal?22:8))),ticks=new Set([data.length-1]);for(let i=0;i<data.length;i+=stride)ticks.add(i);for(const i of [...ticks].sort((a,b)=>a-b)){const row=data[i],label=String(row[spec.xKey]??i);if(horizontal){const short=label.length>31?label.slice(0,29)+'…':label;svg.append(svgNode('text',{x:L-12,y:T+(i+.55)*ih/data.length,'text-anchor':'end',class:'chart-tick'},short));}else if(type!=='scatter'){const xx=type==='bar'?L+(i+.5)*iw/data.length:x(row,i);svg.append(svgNode('text',{x:xx,y:H-B+24,'text-anchor':'middle',class:'chart-tick'},label.length>18?label.slice(0,16)+'…':label));}}
   if(type==='scatter')for(let i=0;i<=4;i++){const v=xmin+(xmax-xmin)*i/4;svg.append(svgNode('text',{x:L+iw*i/4,y:H-B+24,'text-anchor':'middle',class:'chart-tick'},number(v)));}
   if(spec.xAxisLabel&&!horizontal)svg.append(svgNode('text',{x:L+iw/2,y:H-10,'text-anchor':'middle',class:'chart-axis'},spec.xAxisLabel));
   const cursor=svgNode('line',{x1:L,y1:T,x2:L,y2:T+ih,class:'chart-cursor',visibility:'hidden'});svg.append(cursor);let point=0,lastPoint=-1,hoverFrame=0,pendingHover=null,activeBars=[];const barsByPoint=new Map();for(const bar of svg.querySelectorAll('.chart-bar')){const key=+bar.dataset.point;if(!barsByPoint.has(key))barsByPoint.set(key,[]);barsByPoint.get(key).push(bar);}
   function inspect(index,event){point=Math.max(0,Math.min(data.length-1,index));const row=data[point];svg.classList.toggle('chart-inspecting',type==='bar');if(point!==lastPoint){for(const bar of activeBars)bar.classList.remove('chart-active');activeBars=barsByPoint.get(point)||[];for(const bar of activeBars)bar.classList.add('chart-active');tip.replaceChildren(n('strong','chart-tooltip-title',row.material||row.label||row[spec.xKey]||'Saved point'));
    for(const {s,i} of shown){const line=n('div','chart-tooltip-row'),dot=n('span','chart-dot');dot.style.background=seriesColor(i);line.append(dot,n('span','',s.label||s.dataKey),n('strong','',number(row[s.dataKey],s)));tip.append(line);}lastPoint=point;}tip.hidden=false;
    const xx=type==='bar'?L+(point+.5)*iw/data.length:x(row,point);if(!horizontal){cursor.setAttribute('x1',xx);cursor.setAttribute('x2',xx);cursor.setAttribute('visibility','visible');}
    const rect=svg.getBoundingClientRect(),left=event?event.clientX-rect.left:xx/W*rect.width;tip.style.left=Math.max(8,Math.min(rect.width-tip.offsetWidth-8,left+15))+'px';tip.style.top=(event?Math.max(8,Math.min(rect.height-tip.offsetHeight-8,event.clientY-rect.top-15)):15)+'px';
   }
   function move(event){const rect=svg.getBoundingClientRect(),xx=(event.clientX-rect.left)/rect.width*W,yy=(event.clientY-rect.top)/rect.height*H;if(xx<L||xx>W-R||yy<T||yy>T+ih){tip.hidden=true;cursor.setAttribute('visibility','hidden');return;}let index=horizontal?Math.floor((yy-T)/ih*data.length):numericX?ChartMath.nearest(sx,xmin+(xx-L)/iw*(xmax-xmin)):Math.round((xx-L)/iw*(data.length-1));if(type==='scatter'){let best=Infinity;data.forEach((row,i)=>{const distance=(x(row,i)-xx)**2+(y(row[shown[0].s.dataKey])-yy)**2;if(distance<best){best=distance;index=i;}});}inspect(index,event);}
   svg.onpointermove=event=>{pendingHover={clientX:event.clientX,clientY:event.clientY};if(!hoverFrame)hoverFrame=requestAnimationFrame(()=>{hoverFrame=0;move(pendingHover);});};svg._cancelHover=()=>{cancelAnimationFrame(hoverFrame);hoverFrame=0;};
   svg.onpointerleave=()=>{svg._cancelHover();svg.classList.remove('chart-inspecting');tip.hidden=true;cursor.setAttribute('visibility','hidden');};svg.onkeydown=event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();inspect(point+(['ArrowRight','ArrowDown'].includes(event.key)?1:-1));}if(event.key==='Escape'){svg.classList.remove('chart-inspecting');tip.hidden=true;cursor.setAttribute('visibility','hidden');}};
  }
  series.forEach((s,i)=>{const b=n('button','chart-series'),dot=n('span','chart-dot');dot.style.background=seriesColor(i);b.append(dot,document.createTextNode(s.label||s.dataKey));b.setAttribute('aria-pressed','true');b.title='Show or hide this series';b.onclick=()=>{enabled.has(i)?enabled.delete(i):enabled.add(i);b.setAttribute('aria-pressed',String(enabled.has(i)));draw();};legend.append(b);});draw();if(meta.footer)card.append(n('p','widget-footer',meta.footer));
  expand.onclick=()=>{
   const modal=n('dialog','native-chart-modal'),header=n('div','native-chart-modal-header'),name=n('strong','',meta.title||'Chart'),close=n('button','','Close ×'),body=n('div','native-chart-modal-body');
   close.onclick=()=>modal.close();header.append(name,close);body.append(plot,legend);modal.append(header,body);document.body.append(modal);
   modal.addEventListener('close',()=>{card.insertBefore(plot,card.querySelector('.chart-data'));card.insertBefore(legend,card.querySelector('.chart-data'));modal.remove();expand.focus({preventScroll:true});},{once:true});
   modal.showModal();
  };
  const dataFold=n('details','chart-data'),table=n('table'),head=n('thead'),hr=n('tr'),body=n('tbody'),wrap=n('div','table-wrap');const keys=[spec.xKey,...series.map(s=>s.dataKey)].filter(Boolean);keys.forEach((k,i)=>hr.append(n('th','',i===0?(spec.xAxisLabel||k):series[i-1]?.label||k)));head.append(hr);table.append(head,body);let populated=false;dataFold.addEventListener('toggle',()=>{if(!dataFold.open||populated)return;populated=true;for(const row of data.slice(0,1000)){const tr=n('tr');keys.forEach((k,i)=>tr.append(n('td','',i===0?row[k]:number(row[k],series[i-1]))));body.append(tr);}});wrap.append(table);dataFold.append(n('summary','',data.length+' saved data rows'),wrap);card.append(dataFold);if(data.length>1000)dataFold.append(n('p','muted','First 1,000 rows shown. The complete data is in Saved source.'));if(data.length>1600)card.append(n('p','widget-footer','Large chart overview preserves extrema; hover reads the complete saved data.'));source(card,spec);return card;
 }
 function application(spec,context){const card=n('section','saved-widget saved-app');card.append(n('h4','widget-title',spec.title||'Saved app'));const content=String(spec.content||'');
  if(String(spec.language||'').toLowerCase()!=='html'){card.append(n('p','muted','Saved '+(spec.language||'application')+' source'));source(card,content,spec.language||'plaintext');return card;}
  const iframe=n('iframe','artifact-frame');iframe.title=spec.title||'Saved interactive app';iframe.setAttribute('sandbox','allow-scripts');iframe.referrerPolicy='no-referrer';iframe.loading='lazy';
  const nonce=crypto.randomUUID();frames.set(nonce,iframe);for(const [id,frame] of frames)if(id!==nonce&&frame._wasConnected&&!frame.isConnected)frames.delete(id);
  const styles=getComputedStyle(document.documentElement),params=new URLSearchParams({id:context.cid,seq:context.seq,widget:context.index,nonce,...(S.leaf?{leaf:S.leaf}:{})});for(const [key,source] of [['bg','bg'],['text','text'],['muted','muted'],['border','border'],['card','panel'],['accent','accent']])params.set(key,styles.getPropertyValue('--'+source).trim());iframe.src='/api/app-frame?'+params;
  iframe.onload=()=>iframe._wasConnected=true;card.append(iframe,n('p','widget-footer','Saved interactive app · runs locally'));source(card,content,'html','App source');return card;
 }
 function render(value,context={}){try{if(value.image_group)return RichMedia.group(value.image_group,context);if(value.charts_widget_v2){const spec=value.charts_widget_v2.content;return chart(typeof spec==='string'?JSON.parse(spec):spec||{});}if(value.chart)return chart(value.chart);if(value.diagram)return StructuredContent.diagram(value.diagram,source);if(value.downloads){const group=n('section','saved-widget rich-dil-download-list');for(const item of value.downloads)group.append(StructuredContent.layoutRender(item.layout,null,item.source,context));return group;}if(value.layout)return StructuredContent.layoutRender(value.layout,source,value.source,context);if(value.app_block)return application(value.app_block,context);}catch(error){const card=n('section','saved-widget');card.append(n('strong','','Saved widget'),n('p','muted','The saved widget could not be drawn. Its source is available below.'));source(card,value);return card;}
  const card=n('section','saved-widget');card.append(n('strong','',value.unavailable?.title||'Saved widget'));if(!value.unavailable)source(card,value);return card;
 }
 return {extract,render};
})();
