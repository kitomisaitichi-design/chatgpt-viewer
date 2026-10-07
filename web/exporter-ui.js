'use strict';
window.ExportInterop=(()=>{
 let inspection=null,checkId=0,files=[],fileCid='',previewId=0;
 const size=bytes=>{bytes=Number(bytes)||0;return bytes>=1024**2?(bytes/1024**2).toFixed(1)+' MB':(bytes/1024).toFixed(1)+' KB';};
 async function inspect(){
  const path=$('folder-path').value.trim(),id=++checkId,box=$('export-inspection');inspection=null;box.hidden=!path;if(!path)return;
  $('export-inspection-title').textContent='Checking export folder…';$('export-inspection-detail').textContent='';$('use-export-root').hidden=true;
  try{const data=await api('/api/export-inspect?'+new URLSearchParams({path}));if(id!==checkId)return;inspection=data;$('export-inspection-title').textContent=data.format+(data.exporter_version?' · '+data.exporter_version:'');
   $('export-inspection-detail').textContent=data.has_index?[data.available+' saved conversations of '+data.expected,data.missing?data.missing+' still missing':'',data.pending_attachments?data.pending_attachments+' awaiting attachments':'',...data.warnings].filter(Boolean).join(' · '):[data.has_json?'JSON detected':'',data.has_markdown?'Markdown detected':'','Choose Scan & index to load messages and saved files.'].filter(Boolean).join(' · ');
   $('use-export-root').hidden=data.root===path;$('use-export-root').title=data.root;
  }catch(error){if(id===checkId){$('export-inspection-title').textContent='Folder needs attention';$('export-inspection-detail').textContent=error.message;}}
 }
 function getPreviewPane(file){$('saved-files-dialog').close();ThreadAttachments.open(fileCid,file.id||file.relative,null,S.leaf);}
 function assetURL(file){return '/api/asset?'+new URLSearchParams({id:fileCid,path:file.relative});}
 function renderFiles(){const query=$('saved-files-query').value.trim().toLowerCase(),box=$('saved-files-list');box.replaceChildren();
  for(const file of files.filter(f=>(f.name+' '+f.relative).toLowerCase().includes(query))){const row=el('section','saved-file-row'),detail=el('div','saved-file-label');detail.append(el('strong','',file.name),el('span','muted',file.available?size(file.size)+' · Saved locally':'Not downloaded · '+file.status));row.append(detail);
   if(file.available){const preview=el('button','','Preview');preview.onclick=safeRun(()=>showPreview(file));const download=el('a','file-download','Download');download.href=assetURL(file);download.download=file.name;const copy=el('button','icon','⧉');copy.title='Copy original local file path';copy.setAttribute('aria-label',copy.title);copy.onclick=safeRun(async()=>{await navigator.clipboard.writeText(file.path);toast('File path copied');});row.append(preview,download,copy);}box.append(row);
  }
  if(!box.children.length)box.append(el('p','muted',files.length?'No files match your search.':'No attachment records were included in this export. Linked files remain available inside the conversation.'));
 }
 async function showPreview(file){if(!/\.(?:png|jpe?g|gif|webp|avif|bmp)$/i.test(file.name)){getPreviewPane(file);return;}const id=++previewId,box=$('saved-file-preview');box.hidden=false;box.replaceChildren(el('strong','',file.name));
  if(/\.(?:png|jpe?g|gif|webp|avif|bmp)$/i.test(file.name)){const img=el('img');img.alt=file.name;img.loading='lazy';img.src=assetURL(file);img.onerror=()=>box.append(el('p','muted','The saved image could not be displayed.'));box.append(img);return;}
  const pre=el('pre','','Loading preview…');box.append(pre);
  try{const result=await api('/api/file-preview?'+new URLSearchParams({id:fileCid,path:file.relative}));if(id!==previewId)return;pre.textContent=result.text;if(result.truncated)box.append(el('p','muted','First 32 KB shown. Download for the complete file.'));}catch(error){if(id===previewId)pre.textContent=error.message;}
 }
 $('check-export').onclick=safeRun(inspect);$('folder-path').addEventListener('change',()=>safeRun(inspect)());
 $('use-export-root').onclick=safeRun(async()=>{if(!inspection)return;$('folder-path').value=inspection.root;$('scan-up').value='0';await inspect();});
 $('welcome-import').onclick=()=>{$('backup-open').click();$('backup-import-zip').scrollIntoView({block:'nearest'});};
 const openFiles=safeRun(async()=>{if(!S.selected){toast('Open a conversation to see its saved files.');return;}fileCid=S.selected.id;previewId++;files=[];$('saved-files-query').value='';$('saved-file-preview').hidden=true;$('saved-files-title').textContent='Files · '+displayTitle(S.selected);$('saved-files-list').replaceChildren(el('p','muted','Loading saved files…'));modal('saved-files-dialog');const result=await api('/api/saved-files?'+new URLSearchParams({id:fileCid}));files=result.files;$('saved-files-summary').textContent=files.filter(f=>f.available).length+' saved · '+files.filter(f=>!f.available).length+' unavailable';renderFiles();});
 $('saved-files-library').onclick=()=>{$('saved-files-dialog').close();ArchiveFiles.open(fileCid);};
 $('saved-files-query').oninput=renderFiles;$('saved-files-dialog').addEventListener('close',()=>{previewId++;$('saved-file-preview').replaceChildren();});
 return {inspect,openFiles};
})();
