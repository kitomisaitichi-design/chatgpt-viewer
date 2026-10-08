'use strict';
let token;
let searchSource;
addEventListener('message',e=>{if(e.source!==parent||!e.data?.attachmentPreview||e.data.token!==token)return;const d=e.data;
 if(d.action==='zoom')document.getElementById('document').style.zoom=d.scale;
 if(d.action==='search-source'){searchSource=DocumentSearch.snapshot(document.getElementById('document'));parent.postMessage({attachmentPreview:true,token,searchSource:searchSource.text},'*');}
 if(d.action==='search-paint'&&searchSource)DocumentSearch.paint(searchSource,d.hits,d.index,d.all,null,d.reveal);
 if(d.action==='search-clear')DocumentSearch.clear();
});
addEventListener('message',async e=>{if(e.source!==parent||!e.data?.attachmentPreview||e.data.action)return;const data=e.data;token=data.token;try{const zip=await JSZip.loadAsync(data.buffer);for(const name of Object.keys(zip.files)){if(name.endsWith('.rels')){const value=await zip.file(name).async('string');if(/TargetMode\s*=\s*["']External/i.test(value)){const xml=new DOMParser().parseFromString(value,'application/xml');for(const rel of xml.querySelectorAll('Relationship'))if(rel.getAttribute('TargetMode')==='External')rel.remove();zip.file(name,new XMLSerializer().serializeToString(xml));}}}const safe=await zip.generateAsync({type:'arraybuffer'});if(token!==data.token)return;await docx.renderAsync(safe,document.getElementById('document'),null,{renderAltChunks:false,renderComments:false,useBase64URL:true,ignoreLastRenderedPageBreak:false});document.body.style.margin='0';parent.postMessage({attachmentPreview:true,token:data.token,ready:true},'*');}catch(error){parent.postMessage({attachmentPreview:true,token:data.token,error:error.message},'*');}});
