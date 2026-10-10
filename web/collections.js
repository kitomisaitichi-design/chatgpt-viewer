'use strict';
window.Collections=(()=>{
 const selected=new Set(),trashRows=new Map(),bookmarkRows=new Map(),queueRows=new Map(),queueStates=new Map(),completedUntil=new Map(),checkedChats=new Map();let state={jobs:[],bridges:[]},pollTimer=null,polling=false,lastActive='',adding=false,connectionRequest=false,connectionError='',pollError='';
 const pathKey=p=>String(p||'').replaceAll('\\','/').toLocaleLowerCase();
 function currentBridge(){const path=pathKey(S.selected?.path);return state.bridges.find(b=>b.independent&&b.connected)||state.bridges.find(b=>b.root&&path.startsWith(pathKey(b.root)+'/'))||state.bridges.find(b=>b.independent)||(S.selected?null:state.bridges[0]);}
 function connection(){
  const node=$('connection-state'),action=$('connection-connect');if(!node||!action)return;
  const native=state.native_connection||{},connected=native.connected===true,phase=native.phase||'disconnected',signIn=native.alive===true&&phase==='sign-in';
  const label=connected?'Connected to ChatGPT':phase==='starting'?'Starting…':signIn?'Sign in required':phase==='blocked'?'Connection blocked':phase==='error'?'Connection error':'Disconnected';
  const detail=connectionError||pollError||native.error||(connected?'Open the native ChatGPT account window.':signIn?'ChatGPT is open. Sign in in the native window.':phase==='starting'?'The native ChatGPT window is starting.':phase==='blocked'?'The native ChatGPT connection is blocked.':phase==='error'?'The native ChatGPT connection encountered an error.':'Native ChatGPT is disconnected.');
  node.className='connection-state '+(connected?'connected':connectionRequest||phase==='starting'||signIn?'connecting':phase==='blocked'||phase==='error'?'error':'');
  node.lastChild.textContent=label;node.title=detail;
  action.textContent=connected?'Account':connectionRequest?'Connecting…':signIn?'Sign in':'Connect';action.disabled=connectionRequest;action.setAttribute('aria-label',action.textContent);
  action.title=connected?'Open the native ChatGPT account window':signIn?'Bring the native ChatGPT sign-in window forward':detail;
  remoteHeader(S.selected);
 }
 function remoteHeader(c){
  const badge=$('remote-chat-state');if(!badge)return;const nativeRemoved=pathKey(c?.path).includes('/native-codex-recovery/'),unavailable=nativeRemoved||['deleted','unavailable'].includes(c?.remote_state);
  badge.hidden=!unavailable;badge.textContent=nativeRemoved?'Removed from Codex · local copy':c?.remote_state==='deleted'?'Deleted on ChatGPT · local copy':c?.remote_state==='unavailable'?'Unavailable on ChatGPT · local copy':'';badge.title=c?.remote_detail||'Saved transcript and local attachments remain readable.';
  if(unavailable){$('catalog-online').hidden=true;$('continue').hidden=true;}
  const b=currentBridge();if(!c||String(c.path||'').endsWith('.jsonl')||!b?.connected||c.remote_state==='deleted'||b.connection?.blocked||Date.now()/1000-(c.remote_checked||0)<900||Date.now()-(checkedChats.get(c.id)||0)<900000)return;
  checkedChats.set(c.id,Date.now());while(checkedChats.size>1000)checkedChats.delete(checkedChats.keys().next().value);
  // The browser authenticates this read; opening a thread never starts discovery.
  api('/api/remote-status/check',{id:c.id}).catch(error=>{if(S.selected?.id===c.id){const node=$('connection-state');node.title+=' Remote status check: '+error.message;}});
 }
 async function connectAccount(){if(connectionRequest)return;connectionRequest=true;connectionError='';pollError='';connection();try{await api('/api/connection/connect',{});checkedChats.clear();}catch(error){connectionError=error.message||String(error);}finally{connectionRequest=false;connection();await poll();}}
 const button=(label,icon,fn,cls='icon')=>{const b=el('button',cls);b.type='button';b.title=label;b.setAttribute('aria-label',label);ViewerIcons.set(b,icon);b.onclick=safeRun(fn);return b;};
 const pending=()=>state.jobs.filter(j=>!['confirmed','cancelled'].includes(j.state));
 const runnable=()=>pending().filter(j=>!j.local_choice);
 const active=()=>pending().some(j=>['preparing','waiting','running','retrying'].includes(j.state));
 function place(panel){const side=$('sidebar').getBoundingClientRect();panel.style.left=Math.max(8,Math.min(side.right+10,innerWidth-panel.offsetWidth-8))+'px';}
 function renderTrash(){
  const list=$('trash-list'),query=$('trash-filter').value.trim().toLocaleLowerCase(),nodes=[];
  for(const c of S.chats.filter(c=>c.trashed&&displayTitle(c).toLocaleLowerCase().includes(query))){
   let row=trashRows.get(c.id);if(!row){row=el('div','trash-row');row.dataset.id=c.id;row.draggable=true;
    const check=el('input');check.type='checkbox';check.setAttribute('aria-label','Select '+displayTitle(c));check.onchange=()=>{check.checked?selected.add(c.id):selected.delete(c.id);renderTrash();};
    const title=el('button','trash-title');title.onclick=safeRun(()=>openChat(c.id));
    const restore=button('Restore '+displayTitle(c),'undo',async()=>{selected.delete(c.id);await organize(c.id,{trashed:0});renderSidebar();toast('Restored to saved folder');});
    const remove=button('Select '+displayTitle(c)+' for deletion','trash',()=>{selected.has(c.id)?selected.delete(c.id):selected.add(c.id);renderTrash();});remove.classList.add('delete-select');row.append(check,title,restore,remove);
    row.ondragstart=e=>{e.dataTransfer.setData('text/plain',c.id);ChatControls.dragging(true,c.id);};row.ondragend=()=>ChatControls.dragging(false);trashRows.set(c.id,row);
   }
   row.children[0].checked=selected.has(c.id);row.children[1].textContent=displayTitle(c);row.classList.toggle('delete-chosen',selected.has(c.id));row.children[3].setAttribute('aria-pressed',String(selected.has(c.id)));nodes.push(row);
  }
  for(const id of selected)if(!S.chatById.get(id)?.trashed)selected.delete(id);
  if(!nodes.length)nodes.push(el('p','muted',query?'No hidden chats match.':'Trash is empty. Original files are kept.'));
  const outgoing=[...list.children].filter(n=>n.dataset.id&&!nodes.includes(n)&&!S.chatById.get(n.dataset.id)?.trashed);
  for(const row of outgoing){if(row.dataset.leaving)continue;row.dataset.leaving='true';row.inert=true;const height=row.getBoundingClientRect().height;const motion=matchMedia('(prefers-reduced-motion: reduce)').matches;const a=row.animate([{opacity:1,height:height+'px',transform:'translateX(0)'},{opacity:0,height:'0px',paddingTop:0,paddingBottom:0,transform:'translateX(22px)'}],{duration:motion?0:360,easing:'cubic-bezier(.22,1,.36,1)',fill:'forwards'});a.finished.then(()=>{row.remove();trashRows.delete(row.dataset.id);}).catch(()=>{});}
  const arranged=[...nodes];for(const row of outgoing){const next=row.nextElementSibling,index=next?arranged.indexOf(next):-1;arranged.splice(index<0?arranged.length:index,0,row);}SidebarOrder.reconcile(list,arranged);$('trash-count').textContent=String(S.chats.filter(c=>c.trashed).length);
  const queue=$('trash-queue-delete');if(queue){queue.disabled=!selected.size;queue.querySelector('span').textContent='Queue delete ('+selected.size+' selected)';}
  const all=$('trash-select-all'),shown=nodes.filter(n=>n.dataset.id);if(all){all.checked=!!shown.length&&shown.every(n=>selected.has(n.dataset.id));all.indeterminate=shown.some(n=>selected.has(n.dataset.id))&&!all.checked;all.disabled=!shown.length;$('trash-selection-count').textContent=selected.size?selected.size+' selected':S.chats.filter(c=>c.trashed).length+' hidden chats';$('trash-restore-selected').disabled=!selected.size;$('trash-delete-selected').disabled=!selected.size;}
  for(const control of document.querySelectorAll('.trash-current,#trash-panel>.delete-primary'))control.disabled=!S.selected;updateBookmarks();
 }
 function updateBookmarks(){
  const chats=S.chats.filter(c=>c.bookmarked),nav=$('bookmarks-open');if(nav)nav.querySelector('small').textContent=chats.length||'';
  if($('bookmark-current')){$('bookmark-current').disabled=!S.selected;$('bookmark-current').textContent=S.selected?.bookmarked?'Unbookmark current chat':'Bookmark current chat';}
  if(!$('bookmarks-panel')||$('bookmarks-panel').hidden)return;
  const query=$('bookmarks-filter').value.trim().toLocaleLowerCase(),nodes=[];
  for(const c of chats.filter(c=>displayTitle(c).toLocaleLowerCase().includes(query)).sort((a,b)=>a.created-b.created||a.id.localeCompare(b.id))){let row=bookmarkRows.get(c.id);if(!row){row=el('div','trash-row');const title=el('button','trash-title');title.onclick=safeRun(()=>openChat(c.id));row.append(title,button('Unbookmark '+displayTitle(c),'bookmark',async()=>{await organize(c.id,{bookmarked:0});updateBookmarks();}));bookmarkRows.set(c.id,row);}row.children[0].textContent=displayTitle(c);nodes.push(row);}
  if(!nodes.length)nodes.push(el('p','muted','No bookmarks match. Bookmark a chat to keep it here.'));SidebarOrder.reconcile($('bookmarks-list'),nodes);
 }
 function showBookmarks(){const p=$('bookmarks-panel');p.hidden=false;place(p);updateBookmarks();$('bookmarks-filter').focus();}
 const nativeCodex=id=>{const c=S.chatById.get(id);return c?.kind==='codex'&&/\.jsonl$/i.test(c.path||'');};
 let choiceKind='unknown';
 const choiceCopy={
native:{heading:'Delete native Codex session?',warning:'Native Codex session: original file deletion runs locally, without ChatGPT.',delete:'Delete original Codex session and remove it from the viewer',deleteDetail:'Runs locally even while other Codex sessions are open. If this exact JSONL is in use or changing, it retries when available.',preserve:'Keep the original Codex session file; remove it from this viewer',preserveDetail:'Exclude the session from discovery without touching its original file.',notes:'Neither option contacts ChatGPT. Only the selected original JSONL is removed by the first option.'},
  linked:{heading:'Delete ChatGPT-linked conversation?',warning:'Remote deletion is sent only after checking the connected ChatGPT account and saved conversation.',delete:'Delete on ChatGPT and delete the saved local copy',deleteDetail:'ChatGPT must confirm deletion before the original exclusive local source and unshared attachments are removed.',preserve:'Delete on ChatGPT but preserve the original local copy',preserveDetail:'After ChatGPT confirms deletion, keep the saved source file on disk and remove the chat from this viewer index.',notes:'Both options delete the ChatGPT chat. The first also removes its exclusive local original; the second keeps that file.'},
  orphan:{heading:'Delete local-only conversation?',warning:'No verified ChatGPT account or original online link is associated with this saved chat.',delete:'Delete this local-only source file and its viewer index',deleteDetail:'Remove the original file only if it contains this conversation alone. Other files remain untouched.',preserve:'Keep the original local file; remove it from the viewer',preserveDetail:'Leave the source file in its folder and exclude the conversation from rescanning.',notes:'No ChatGPT request is made for either choice.'},
  temporary:{heading:'Delete saved temporary chat?',warning:'This chat is marked temporary in the original ChatGPT export. It is handled locally; ChatGPT deletion is not required.',delete:'Delete saved temporary chat file and remove it from the viewer',deleteDetail:'Remove the exclusive local original and its viewer index; prevent rediscovery.',preserve:'Keep temporary chat file; remove it from the viewer',preserveDetail:'Keep the original file in its folder, remove its index entry and prevent rediscovery.',notes:'Neither option contacts ChatGPT. Temporary chat status overrides any inferred ChatGPT URL.'},
  unknown:{heading:'Unverified conversation source',warning:'The viewer cannot establish an original ChatGPT account or prove this is an orphan. Remote and physical deletion are disabled.',delete:'Deletion unavailable until source is identified',deleteDetail:'No file or remote chat will be deleted on an inferred URL.',preserve:'Keep original source; remove it from the viewer only',preserveDetail:'Exclude this chat from the viewer index without changing the source file or ChatGPT.',notes:'Viewer URLs can be generated from chat IDs; they do not establish ChatGPT ownership.'}
 };
 function refreshChoice(){
  const spec=choiceCopy[choiceKind],mode=document.querySelector('[name=delete-retention]:checked')?.value||'library';
  $('delete-choice-add').textContent=mode==='library'?(choiceKind==='linked'?'Queue ChatGPT + local deletion':'Queue local deletion'):choiceKind==='linked'?'Queue ChatGPT deletion · keep local file':'Remove from viewer only';
  $('delete-choice-warning').textContent=mode==='preserve'?(choiceKind==='linked'?'ChatGPT deletion is still required and cannot be undone. The original local file will be retained.':'Keep the original source file. Remove only this viewer entry; no ChatGPT deletion is requested.'):spec.warning;
  $('delete-choice-notes').textContent=spec.notes;
 }
 async function stage(ids){
  if(!ids.length)return;
  const response=await api('/api/delete-choice/inspect',{ids});
  const kinds=[...new Set(response.choices.map(c=>c.kind))];
  if(kinds.length!==1){toast('Select one chat source type at a time: Codex, ChatGPT-linked, temporary or local-only.');return;}
  choiceKind=kinds[0];const spec=choiceCopy[choiceKind],dialog=$('delete-choice');
  const library=document.querySelector('[name=delete-retention][value=library]'),preserve=document.querySelector('[name=delete-retention][value=preserve]');
  library.closest('label').querySelector('span').firstChild.textContent=spec.delete;
  library.closest('label').querySelector('small').textContent=spec.deleteDetail;
  preserve.closest('label').querySelector('span').firstChild.textContent=spec.preserve;
  preserve.closest('label').querySelector('small').textContent=spec.preserveDetail;
  library.disabled=choiceKind==='unknown';preserve.checked=choiceKind==='unknown';library.checked=choiceKind!=='unknown';
  $('delete-choice-title').textContent=spec.heading;
  $('delete-choice-warning').textContent=spec.warning;
  $('delete-choice-count').textContent=ids.length+' conversation'+(ids.length===1?'':'s');
  let sourceChoices=$('delete-choice-origins');
  if(!sourceChoices){sourceChoices=el('section','delete-origin-list');sourceChoices.id='delete-choice-origins';dialog.querySelector('.delete-options').before(sourceChoices);}
  sourceChoices.replaceChildren();
  for(const item of response.choices.filter(c=>c.origins?.length>1)){
   const label=el('label','delete-origin-item'),title=el('strong','',item.title),select=el('select');
   select.dataset.chatId=item.id;select.setAttribute('aria-label','Original export for '+item.title);
   const placeholder=el('option','','Choose an original export…');placeholder.value='';select.append(placeholder);
   for(const origin of item.origins){const option=el('option','',origin.label+' · Scope '+origin.scope_hint+(origin.displayed?' · Displayed source':''));option.value=origin.root;option.title=origin.root;select.append(option);}
   label.append(title,select);sourceChoices.append(label);
  }
  sourceChoices.hidden=!sourceChoices.childElementCount;
  dialog.dataset.ids=JSON.stringify(ids);refreshChoice();dialog.showModal();
 }
 async function add(){
  if(adding)return;adding=true;$('delete-choice-add').disabled=true;
  try{
   const ids=JSON.parse($('delete-choice').dataset.ids);
   const mode=document.querySelector('[name=delete-retention]:checked').value==='library'?'delete':'preserve';
   const origins={};
   for(const select of $('delete-choice-origins').querySelectorAll('select')){
    if(!select.value){select.focus();toast('Choose the original export for each chat before queueing deletion.');return;}
    origins[select.dataset.chatId]=select.value;
   }
   const response=await api('/api/delete-choice/submit',{ids,mode,origins});
   $('delete-choice').close();selected.clear();renderTrash();
   toast(choiceKind==='linked'?(mode==='preserve'?'Queued ChatGPT deletion; original local file will be kept.':'Queued ChatGPT deletion and subsequent local removal.'):mode==='preserve'?'Keeping original file; removing only from viewer.':'Queued local deletion without ChatGPT.');
   await showQueue();
  }finally{adding=false;$('delete-choice-add').disabled=false;}
 }
 function renderQueue(){
  const jobs=state.jobs.filter(j=>j.state!=='cancelled'),waiting=pending(),remoteJobs=runnable(),doing=active(),dialog=$('delete-queue-dialog'),list=$('delete-queue-list'),nodes=[];
  $('delete-queue-open').hidden=!waiting.length;$('delete-queue-open').textContent=doing?'Deleting · '+jobs.filter(j=>j.state==='confirmed').length+'/'+jobs.length:'Queue delete · '+waiting.length;
  // Completed/failed jobs may retain historical retry timestamps. Only an
  // actively retrying job is allowed to drive the visible countdown.
  const cooling=waiting.filter(j=>j.state==='retrying'&&j.until>Date.now()/1000).sort((a,b)=>a.until-b.until)[0],deferred=jobs.some(j=>j.state==='waiting'&&j.local);
  const linked=remoteJobs.filter(j=>!j.local),independent=new Set((state.bridges||[]).filter(b=>b.independent&&b.connected).map(b=>b.scope));
  const remoteReady=linked.every(j=>j.proof_ready||(independent.size>0&&(j.scope==='unbound'||independent.has(j.scope))));
  const awaitingConnection=linked.length>0&&!remoteReady;
  $('delete-queue-title').textContent=awaitingConnection?'Waiting for ChatGPT connection':cooling?'Waiting':doing?(deferred?'Waiting for selected file':'Running'):waiting.length?'Review deletion queue':jobs.length?'Done':'Deletion queue';
  $('delete-queue-dialog').classList.toggle('queue-active',doing&&!awaitingConnection);$('delete-queue-dialog').dataset.phase=!jobs.length?'empty':awaitingConnection||cooling||deferred?'waiting':doing?'running':waiting.length?'review':'done';
  $('delete-queue-countdown').hidden=!cooling;if(cooling){const seconds=Math.max(0,Math.ceil(cooling.until-Date.now()/1000));$('delete-queue-countdown').textContent=Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');$('delete-queue-countdown').title=cooling.message||cooling.error||'Waiting for retry';}
  $('delete-queue-count').textContent=jobs.filter(j=>j.state==='confirmed').length+' / '+jobs.length;
  const complete=jobs.filter(j=>j.state==='confirmed').length,progress=$('delete-queue-progress');progress.max=Math.max(jobs.length,1);progress.value=complete;const fill=$('delete-queue-fill');if(fill)fill.style.width=100*complete/Math.max(jobs.length,1)+'%';
  const native=state.native_connection||{},phase=native.phase||'disconnected';
  const needsRemote=remoteJobs.some(j=>!j.local);
  const verifiedLocally=linked.length>0&&linked.every(j=>j.proof_ready);
  $('delete-queue-connection').textContent=!needsRemote?'Local work only · ChatGPT connection not required':verifiedLocally?'Online deletion is already verified. Local cleanup can run without reconnecting.':independent.size>0&&!remoteReady?'Wrong ChatGPT account for this saved export. Open the account connection and switch to the matching account.':remoteReady?'Connected to matching ChatGPT account':phase==='starting'?'Starting ChatGPT…':native.alive===true&&phase==='sign-in'?'Sign in to ChatGPT to continue.':phase==='blocked'||phase==='error'?native.error||'ChatGPT connection unavailable. Use Connect to try again.':'No connected ChatGPT worker in this Viewer. Nothing has been sent. Click Connect and sign in to the account that owns the selected export.';
  let queueConnect=$('delete-queue-connect');if(!queueConnect){queueConnect=el('button','','Connect ChatGPT account');queueConnect.id='delete-queue-connect';queueConnect.onclick=safeRun(connectAccount);$('delete-queue-connection').after(queueConnect);}
  queueConnect.hidden=!awaitingConnection;queueConnect.textContent=independent.size?'Switch ChatGPT account':'Connect ChatGPT account';queueConnect.disabled=connectionRequest;
  $('delete-queue-notes').textContent=cooling?((cooling.message||cooling.error||'Retry pending')+' · ChatGPT rate limits and local browser traffic use separate timers.'):verifiedLocally?'Matching deletion receipts are already verified. Remaining files are processed using local recovery and checksum checks.':needsRemote?'ChatGPT-linked jobs require authenticated confirmation before removing local files. Native Codex and local-only operations run independently.':'Only the selected original Codex file must be available for local deletion. Other Codex sessions may stay open. No ChatGPT connection is required.';
  dialog.querySelector('.delete-warning').hidden=!waiting.some(job=>!job.local);connection();
  for(const job of jobs){const previous=queueStates.get(job.id);queueStates.set(job.id,job.state);
   if(job.state==='confirmed'){
    if(previous&&previous!=='confirmed'||job.local_choice&&previous===undefined){completedUntil.set(job.id,Date.now()+1400);setTimeout(renderQueue,1450);}
    if(!completedUntil.has(job.id))continue;
    if(Date.now()>=completedUntil.get(job.id)){const old=queueRows.get(job.id);if(old&&!old.dataset.leaving){old.dataset.leaving='true';old.inert=true;const height=old.getBoundingClientRect().height;const motion=matchMedia('(prefers-reduced-motion: reduce)').matches;old.animate([{opacity:.7,height:height+'px'},{opacity:0,height:'0px',minHeight:0,paddingTop:0,paddingBottom:0}],{duration:motion?0:380,easing:'cubic-bezier(.22,1,.36,1)',fill:'forwards'}).finished.then(()=>{old.remove();queueRows.delete(job.id);completedUntil.delete(job.id);}).catch(()=>{});}if(old)nodes.push(old);continue;}
   }
   let row=queueRows.get(job.id);if(!row){row=el('div','delete-job');row.dataset.id=job.id;row.append(el('span','delete-job-state'),el('div','delete-job-title'),button('Remove queued deletion','close',async()=>{state=await api('/api/delete-queue/action',{action:'remove',ids:[job.id]});renderQueue();}));queueRows.set(job.id,row);}row.className='delete-job '+job.state;if(row.dataset.state!==job.state){row.dataset.state=job.state;row.children[0].replaceChildren();if(job.state==='confirmed')row.children[0].append(ViewerIcons.svg('check'));else row.children[0].textContent=job.state==='preparing'?'Preparing deletion':job.state==='waiting'?(job.local?'Waiting for file':'Waiting for ChatGPT'):job.state==='running'?(job.local?'Removing locally':'Deleting on ChatGPT'):({queued:'Queued',retrying:'Checking result',paused:'Paused',failed:'Attention'})[job.state]||job.state;}
   if(!row.children[1].children.length)row.children[1].append(el('strong'),el('small','muted'));
   const detail=job.error||(job.local_choice?(job.mode==='preserve'?'Keep original file; remove only from viewer index':'Delete exclusive local-only source and index'):job.local?(job.mode==='library'?'Remove original Codex session and index':'Keep readable local Codex recovery in Trash'):job.mode==='library'?'Delete on ChatGPT, then remove exclusive local sources':'Delete on ChatGPT; keep original local source and hide viewer entry after confirmation');
   row.children[1].children[0].textContent=job.title;row.children[1].children[1].textContent=detail;
   row.children[2].hidden=job.local_choice||!['queued','paused','failed'].includes(job.state);nodes.push(row);
  }
  if(!nodes.length)nodes.push(el('p','muted',jobs.length&&!waiting.length?'All deletions finished.':'The deletion queue is empty. Select chats in Trash to add them.'));SidebarOrder.reconcile(list,nodes);
  const current=jobs.find(j=>['preparing','running','retrying','waiting'].includes(j.state))||jobs.filter(j=>j.state==='confirmed'&&completedUntil.has(j.id)).at(-1);
  const scrollKey=current?current.id+':'+current.state:'';
  if(scrollKey&&scrollKey!==lastActive&&dialog.open){const row=queueRows.get(current.id);requestAnimationFrame(()=>{if(!dialog.open||!row?.isConnected)return;const target=row.getBoundingClientRect().top-list.getBoundingClientRect().top+list.scrollTop-(list.clientHeight-row.offsetHeight)/2;list.scrollTo({top:Math.max(0,target),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});lastActive=scrollKey;}
  $('delete-queue-run').hidden=doing||!remoteJobs.length;$('delete-queue-pause').hidden=!remoteJobs.length;$('delete-queue-stop').hidden=!remoteJobs.length;$('delete-queue-run').disabled=doing||!remoteJobs.length||awaitingConnection;$('delete-queue-run').textContent='Run '+remoteJobs.length+' deletion'+(remoteJobs.length===1?'':'s');$('delete-queue-pause').disabled=!doing;$('delete-queue-stop').disabled=!doing;
  updateBookmarks();
 }
 async function poll(){if(polling)return;polling=true;try{state=await api('/api/delete-queue');removeCatalog(state.removed);pollError='';renderQueue();renderTrash();}catch(e){pollError=e.message||String(e);$('delete-queue-connection').textContent='Could not refresh deletion queue · '+pollError;connection();}finally{polling=false;clearTimeout(pollTimer);pollTimer=setTimeout(poll,document.hidden?30000:active()||$('delete-queue-dialog').open||state.native_connection?.alive&&!state.native_connection?.connected?1500:15000);}}
 async function showQueue(){lastActive='';const d=$('delete-queue-dialog');if(!d.open)d.showModal();await poll();}
 async function queueAction(action){const b=$('delete-queue-'+(action==='run'?'run':action));b.disabled=true;try{state=await api('/api/delete-queue/action',{action,ids:runnable().map(j=>j.id)});renderQueue();}finally{await poll();}}
 async function discover(){const b=$('native-discover');b.disabled=true;try{await api('/api/codex/discover',{});for(;;){const value=await api('/api/codex/status');$('native-status').textContent=(value.running?'Discovering native sessions… ':'Native Codex: ')+value.found+' available'+(value.errors.length?' · '+value.errors.join('; '):'');if(!value.running)break;await new Promise(r=>setTimeout(r,1500));}}finally{b.disabled=false;}}
 function init(){
  const bridgeStatus=el('span','connection-state');bridgeStatus.id='connection-state';bridgeStatus.setAttribute('role','status');bridgeStatus.append(el('span','connection-dot'),document.createTextNode('Disconnected'));const connect=el('button','','Connect');connect.id='connection-connect';connect.onclick=safeRun(connectAccount);const group=el('span','connection-group');group.append(bridgeStatus,connect);$('message-stat').after(group);const remote=el('span','remote-chat-state');remote.id='remote-chat-state';remote.hidden=true;$('catalog-message-count').after(remote);
  const trash=$('trash-panel'),footer=el('div','collection-footer'),queue=el('button','delete-primary','Queue delete');queue.replaceChildren(ViewerIcons.svg('trash'),el('span','','Queue delete (0 selected)'));queue.id='trash-queue-delete';queue.onclick=safeRun(()=>stage([...selected]));footer.append(queue);trash.append(footer);
  const heading=trash.querySelector('h3'),badge=el('span','collection-badge');badge.append(ViewerIcons.svg('trash'));heading.prepend(badge);ViewerIcons.set($('trash-close'),'close');
  const filter=$('trash-filter'),searchBox=el('div','collection-search');filter.before(searchBox);searchBox.append(ViewerIcons.svg('search'),filter);
  const tools=el('div','trash-tools'),all=el('input');all.id='trash-select-all';all.type='checkbox';all.setAttribute('aria-label','Select all visible hidden chats');all.onchange=()=>{for(const c of S.chats.filter(c=>c.trashed&&displayTitle(c).toLocaleLowerCase().includes(filter.value.trim().toLocaleLowerCase())))all.checked?selected.add(c.id):selected.delete(c.id);renderTrash();};
  const count=el('span');count.id='trash-selection-count';const restore=button('Restore selected chats','undo',async()=>{const ids=[...selected];await api('/api/organize-many',{changes:ids.map(id=>({id,trashed:0}))});for(const id of ids){Object.assign(S.chatById.get(id)||{},{trashed:0});localOrganization.set(id,{...(localOrganization.get(id)||{}),trashed:0});}selected.clear();renderSidebar();renderTrash();},'trash-bulk');restore.id='trash-restore-selected';restore.append(document.createTextNode('Restore'));
  const remove=button('Queue selected chats for deletion','trash',()=>stage([...selected]),'trash-bulk');remove.id='trash-delete-selected';remove.append(document.createTextNode('Delete'));tools.append(all,count,restore,remove);$('trash-list').before(tools);
  const progress=$('delete-queue-progress'),track=el('div','queue-progress-track'),fill=el('div');fill.id='delete-queue-fill';progress.after(track);track.append(fill);track.setAttribute('aria-hidden','true');progress.classList.add('sr-progress');
  const current=el('button','','Move current chat to Trash');current.onclick=safeRun(async()=>{if(!S.selected)return;await organize(S.selected.id,{trashed:1});renderSidebar();renderTrash();});current.replaceChildren(ViewerIcons.svg('undo'),document.createTextNode('Move current chat to Trash'));current.className='trash-current';trash.insertBefore(current,searchBox);
  const p=el('section','collection-panel');p.id='bookmarks-panel';p.hidden=true;p.setAttribute('role','dialog');p.setAttribute('aria-label','Bookmarks');const head=el('div','trash-heading');head.append(el('h3','','Bookmarks'),button('Close Bookmarks','close',()=>{p.hidden=true;}));const toggle=el('button');toggle.id='bookmark-current';toggle.onclick=safeRun(async()=>{if(!S.selected)return;await organize(S.selected.id,{bookmarked:S.selected.bookmarked?0:1});updateBookmarks();});const search=el('input');search.id='bookmarks-filter';search.type='search';search.placeholder='Find a bookmarked chat';search.setAttribute('aria-label',search.placeholder);search.oninput=updateBookmarks;const list=el('div');list.id='bookmarks-list';p.append(head,toggle,search,list);document.body.append(p);
  const nav=el('button','nav-action trash-nav');nav.id='bookmarks-open';nav.append(ViewerIcons.svg('bookmark'),document.createTextNode('Bookmarks'),el('small'));nav.onclick=showBookmarks;$('trash-open').before(nav);
  const queueNav=el('button','delete-primary');queueNav.id='delete-queue-open';queueNav.hidden=true;queueNav.onclick=safeRun(showQueue);$('trash-open').after(queueNav);
  const toolbar=document.querySelector('.header-right');toolbar.insertBefore(button('Open Bookmarks','bookmark',showBookmarks),$('chat-menu'));toolbar.insertBefore(button('Open Trash','trash',()=>ChatControls.showTrash()),$('chat-menu'));
  document.querySelectorAll('[name=delete-retention]').forEach(input=>input.onchange=refreshChoice);
  $('delete-choice-add').onclick=safeRun(add);$('delete-queue-run').onclick=safeRun(()=>queueAction('run'));$('delete-queue-pause').onclick=safeRun(()=>queueAction('pause'));$('delete-queue-stop').onclick=safeRun(()=>queueAction('stop'));
  const deleteCurrent=el('button','delete-primary','Queue deletion of current chat');deleteCurrent.onclick=safeRun(()=>S.selected&&stage([S.selected.id]));deleteCurrent.replaceChildren(ViewerIcons.svg('trash'),document.createTextNode('Queue deletion of current chat'));trash.insertBefore(deleteCurrent,searchBox);
  const native=el('section','native-discovery'),nativeButton=el('button','','Detect native Codex chats');nativeButton.id='native-discover';nativeButton.onclick=safeRun(discover);const status=el('p','muted');status.id='native-status';status.setAttribute('role','status');status.textContent='Uses CODEX_HOME or your Windows profile .codex folder. Session bodies load when opened.';const nativeToggle=el('label','check'),nativeCheck=el('input');nativeCheck.type='checkbox';nativeCheck.id='native-startup';nativeCheck.checked=S.settings.nativeCodexEnabled!==false;nativeCheck.onchange=safeRun(()=>saveSetting('nativeCodexEnabled',nativeCheck.checked));nativeToggle.append(nativeCheck,document.createTextNode('Discover native Codex at startup'));native.append(nativeButton,nativeToggle,status);$('folder-dialog').append(native);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')p.hidden=true;});window.addEventListener('resize',()=>{if(!p.hidden)place(p);});document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});updateBookmarks();poll();
 }
 document.addEventListener('DOMContentLoaded',init);return {renderTrash,updateBookmarks,showBookmarks,showQueue,stage,remoteHeader,connection};
})();
