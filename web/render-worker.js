'use strict';
// Core Markdown and optional syntax colouring have independent lifecycles.
const ASSETS={marked:'vendor/marked.js',highlight:'vendor/highlight.js'};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function fetchAsset(url,timeout,json=false){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);try{const response=await fetch(url,{signal:controller.signal});if(!response.ok)throw Error('Renderer asset returned '+response.status);return await(json?response.json():response.text());}finally{clearTimeout(timer);}}
function evaluateAsset(text){const url=URL.createObjectURL(new Blob([text],{type:'text/javascript'}));try{importScripts(url);}finally{URL.revokeObjectURL(url);}}
async function loadBundled(name){
 try{evaluateAsset(await fetchAsset(ASSETS[name]+'?v=1.0.11',3000));return;}catch{}
 let text='',offset=0,deadline=Date.now()+9000;
 while(true){let part,last;
  for(let attempt=0;attempt<3;attempt++){const remaining=deadline-Date.now();if(remaining<=0)throw Error(name+' renderer download timed out');try{part=await fetchAsset('/api/renderer?name='+name+'&offset='+offset,Math.min(1800,remaining),true);break;}catch(error){last=error;if(attempt<2)await pause(100*(attempt+1));}}
  if(!part)throw last;
  if(!part.done&&part.next<=offset)throw Error('Renderer download did not advance');
  text+=part.text;offset=part.next;if(part.done)break;
 }
 evaluateAsset(text);
}
let highlighting=null,highlightFailures=0;
function highlighter(){
 if(self.hljs)return Promise.resolve(true);
 if(!highlighting)highlighting=loadBundled('highlight').then(()=>{postMessage({highlightReady:true});return true;}).catch(()=>{highlighting=null;if(++highlightFailures<3)setTimeout(highlighter,1000*highlightFailures);return false;});
 return highlighting;
}
loadBundled('marked').then(()=>{postMessage({ready:true});highlighter();}).catch(error=>postMessage({startupError:error.message}));
const escape=text=>text.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Validate JSON, but preserve numeric tokens verbatim (JSON.parse/stringify
// alone can round large integers). Only string escapes and layout change.
function readableJSON(text){JSON.parse(text);let out='',depth=0,last='',i=0;const newline=()=>{out+='\n'+'  '.repeat(depth);};while(i<text.length){const c=text[i];if(/\s/.test(c)){i++;continue;}if(c==='"'){const start=i++;while(i<text.length){if(text[i]==='\\'){i+=2;continue;}if(text[i++]==='"')break;}out+=JSON.stringify(JSON.parse(text.slice(start,i)));last='string';continue;}i++;if(c==='{'||c==='['){out+=c;depth++;if(!/^[\s]*[}\]]/.test(text.slice(i)))newline();}else if(c==='}'||c===']'){depth--;if(last!=='{'&&last!=='[')newline();out+=c;}else if(c===','){out+=',';newline();}else if(c===':')out+=': ';else{const start=i-1;while(i<text.length&&!/[\s,}\]]/.test(text[i]))i++;out+=text.slice(start,i);}last=c;}return out;}
onmessage=async event=>{const {id,text,mode='markdown',language='plaintext'}=event.data;try{
 if(mode==='highlight'){let html=escape(text);if(self.hljs&&hljs.getLanguage(language)&&text.length<250000){try{html=hljs.highlight(text,{language,ignoreIllegals:true}).value;}catch{}}postMessage({id,html});return;}
 if(mode!=='markdown'){let display=text;if(mode==='code'&&language==='json'){try{display=readableJSON(text);}catch{}}let html=escape(display);if(mode==='code'&&display.length<250000){highlighter();if(self.hljs&&hljs.getLanguage(language)){try{html=hljs.highlight(display,{language,ignoreIllegals:true}).value;}catch{}}}postMessage({id,html:'<pre><code class="language-'+language+'">'+html+'</code></pre>'});return;}
 const tokens=marked.lexer(text,{gfm:true,breaks:false}),codes=[];
 function visit(items){for(const t of items){if(t.type==='code')codes.push(t);if(t.tokens)visit(t.tokens);if(t.items)visit(t.items);}}
 visit(tokens);if(codes.some(t=>t.lang))highlighter();
 const renderer=new marked.Renderer();renderer.code=token=>{let lang=(token.lang||'').split(/\s+/)[0].toLowerCase().replace(/[^\w+-]/g,''),html=escape(token.text);if(lang&&self.hljs&&hljs.getLanguage(lang)&&token.text.length<250000){try{html=hljs.highlight(token.text,{language:lang,ignoreIllegals:true}).value;}catch{}}return '<pre><code'+(lang?' class="language-'+lang+'"':'')+'>'+html+'</code></pre>\n';};
 postMessage({id,html:marked.parser(tokens,{gfm:true,breaks:false,renderer})});
 }catch(error){postMessage({id,error:error.message});}};
