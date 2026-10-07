'use strict';
window.Collections=(()=>{
 const selected=new Set(),trashRows=new Map(),bookmarkRows=new Map(),queueRows=new Map(),checkedChats=new Map();let state={jobs:[],bridges:[]},pollTimer=null,polling=false,follow=true,lastActive='',adding=false,reconnecting=false;
 const pathKey=p=>String(p||'').replaceAll('\\','/').toLocaleLowerCase();
 function currentBridge(){const path=pathKey(S.selected?.path);return state.bridges.find(b=>b.independent&&b.connected)||state.bridges.find(b=>b.root&&path.startsWith(pathKey(b.root)+'/'))||state.bridges.find(b=>b.independent)||(S.selected?null:state.bridges[0]);}
 function connection(){
  const node=$('connection-state'),retry=$('connection-reconnect');if(!node)return;
  const b=currentBridge()||(!S.selected?.url?state.bridges[0]:null),c=b?.connection||{},busy=reconnecting||b?.reconnecting;
  let label=b?.connected?'Connected':busy?'Reconnecting…':c.blocked?'Reconnect needed':b?.fresh&&c.attempts>0?'Retry '+Math.min(c.attempts,2)+' / 2':'Disconnected';
  node.className='connection-state '+(b?.connected?'connected':busy||b?.fresh&&c.attempts>0&&!c.blocked?'connecting':'');
  node.lastChild.textContent=label;node.title=b?.connected?'ChatGPT browser bridge · authenticated account matches':c.error||'ChatGPT browser bridge disconnected. Local reading remains available.';
  retry.hidden=!!b?.connected;retry.disabled=busy;retry.title='Reset the two-retry budget and reconnect to your signed-in ChatGPT tab';
  remoteHeader(S.selected);
 }
 function remoteHeader(c){
  const badge=$('remote-chat-state');if(!badge)return;const nativeRemoved=pathKey(c?.path).includes('/native-codex-recovery/'),unavailable=nativeRemoved||['deleted','unavailable'].includes(c?.remote_state);
  badge.hidden=!unavailable;badge.textContent=nativeRemoved?'Removed from Codex · local copy':c?.remote_state==='deleted'?'Deleted on ChatGPT · local copy':c?.remote_state==='unavailable'?'Unavailable on ChatGPT · local copy':'';badge.title=c?.remote_detail||'Saved transcript and local attachments remain readable.';
  if(unavailable){$('catalog-online').hidden=true;$('continue').hidden=true;}
  const b=currentBridge();if(!c||String(c.path||'').endsWith('.jsonl')||!b?.connected||c.remote_state==='deleted'||b.connection?.blocked||Date.now()/1000-(c.remote_checked||0)<900||Date.now()-(checkedChats.get(c.id)||0)<900000)return;
  checkedChats.set(c.id,Date.now());while(checkedChats.size>1000)checkedChats.delete(checkedChats.keys().next().value);
  // The browser authenticates this read; opening a thread never starts discovery.
  api('/api/remote-status/check',{id:c.id}).catch(error=>{if(S.selected?.id===c.id)$('connection-state').title=error.message;});
 }
 async function reconnect(){if(reconnecting)return;reconnecting=true;connection();try{const r=await api('/api/connection/reconnect',{});toast(r.message);checkedChats.clear();}finally{reconnecting=false;await poll();}}
 const button=(label,icon,fn,cls='icon')=>{const b=el('button',cls);b.type='button';b.title=label;b.setAttribute('aria-label',label);ViewerIcons.set(b,icon);b.onclick=safeRun(fn);return b;};
 const pending=()=>state.jobs.filter(j=>!['confirmed','cancelled'].includes(j.state));
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
  SidebarOrder.reconcile(list,nodes);$('trash-count').textContent=String(S.chats.filter(c=>c.trashed).length);
  const queue=$('trash-queue-delete');if(queue){queue.disabled=!selected.size;queue.textContent='Queue delete'+(selected.size?' · '+selected.size:'');}
  updateBookmarks();
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
 async function stage(ids){if(!ids.length)return;const dialog=$('delete-choice');const local=ids.every(id=>String(S.chatById.get(id)?.path||'').endsWith('.jsonl'));const library=document.querySelector('[name=delete-retention][value=library]'),preserve=document.querySelector('[name=delete-retention][value=preserve]');library.closest('label').hidden=local;library.checked=!local;preserve.checked=local;$('delete-choice-warning').textContent=local?'Remove these native Codex sessions locally. Recovery copies are retained; execution waits until Codex is closed.':'Deleting in ChatGPT is permanent. Native Codex sessions are removed locally after Codex closes. Adding to this queue does not run it.';dialog.dataset.ids=JSON.stringify(ids);$('delete-choice-count').textContent=ids.length+' conversation'+(ids.length===1?'':'s');dialog.showModal();}
 async function add(){if(adding)return;adding=true;$('delete-choice-add').disabled=true;try{state=await api('/api/delete-queue/add',{ids:JSON.parse($('delete-choice').dataset.ids),mode:document.querySelector('[name=delete-retention]:checked').value});$('delete-choice').close();selected.clear();renderTrash();await showQueue();}finally{adding=false;$('delete-choice-add').disabled=false;}}
 function renderQueue(){
  const jobs=state.jobs.filter(j=>j.state!=='cancelled'),waiting=pending(),doing=active(),dialog=$('delete-queue-dialog'),list=$('delete-queue-list'),nodes=[];
  $('delete-queue-open').hidden=!jobs.length;$('delete-queue-open').textContent=doing?'Deleting · '+jobs.filter(j=>j.state==='confirmed').length+'/'+jobs.length:'Queue delete · '+waiting.length;
  const cooling=jobs.find(j=>j.until>Date.now()/1000),deferred=jobs.some(j=>j.state==='waiting'&&j.local);
  $('delete-queue-title').textContent=cooling?'Waiting':doing?(deferred?'Waiting for Codex to close':'Running'):waiting.length?'Review deletion queue':jobs.length?'Done':'Browser connection';
  $('delete-queue-dialog').classList.toggle('queue-active',doing);$('delete-queue-dialog').dataset.phase=cooling||deferred?'waiting':doing?'running':waiting.length?'review':'done';
  $('delete-queue-countdown').hidden=!cooling;if(cooling){const seconds=Math.max(0,Math.ceil(cooling.until-Date.now()/1000));$('delete-queue-countdown').textContent=Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');}
  $('delete-queue-count').textContent=jobs.filter(j=>j.state==='confirmed').length+' / '+jobs.length;
  $('delete-queue-progress').max=Math.max(jobs.length,1);$('delete-queue-progress').value=jobs.filter(j=>j.state==='confirmed').length;
  if(!$('exporter-adapter-path').value&&state.adapter_folder)$('exporter-adapter-path').value=state.adapter_folder;
  $('delete-queue-connection').textContent=state.bridges.some(b=>b.connected)?'Connected · '+(state.bridges.some(b=>b.connected&&b.owner==='exporter')?'exporter handles the queue':'independent viewer connection'):state.bridges.some(b=>b.connection?.blocked)?'Reconnect needed · two automatic retries failed. Use Reconnect in the status bar.':'Connect your browser below · no exporter is required. Local Codex jobs wait for Codex to close.';connection();
  for(const job of jobs){let row=queueRows.get(job.id);if(!row){row=el('div','delete-job');row.dataset.id=job.id;row.append(el('span','delete-job-state'),el('div','delete-job-title'),button('Remove queued deletion','close',async()=>{state=await api('/api/delete-queue/action',{action:'remove',ids:[job.id]});renderQueue();}));queueRows.set(job.id,row);}row.className='delete-job '+job.state;row.children[0].replaceChildren();if(job.state==='confirmed')row.children[0].append(ViewerIcons.svg('check'));else row.children[0].textContent=({queued:'Queued',preparing:'Backing up',waiting:'Waiting',running:'Running',retrying:'Cooldown',paused:'Paused',failed:'Attention'})[job.state]||job.state;
   row.children[1].replaceChildren(el('strong','',job.title),el('small','muted',job.error||job.message||(job.local?'Local Codex · recovery retained':job.remote_state==='unavailable'?'Unavailable on ChatGPT · local files retained':job.mode==='preserve'?'Preserve local copy':'Clean up unshared local Library copies · recovery retained')));row.children[2].hidden=!['queued','paused','failed'].includes(job.state);nodes.push(row);
  }
  if(!nodes.length)nodes.push(el('p','muted','The deletion queue is empty. Select chats in Trash to add them.'));SidebarOrder.reconcile(list,nodes);
  const current=jobs.find(j=>['preparing','running','retrying','waiting'].includes(j.state))?.id;if(follow&&current&&current!==lastActive&&!dialog.hidden&&dialog.open)queueRows.get(current)?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'nearest'});lastActive=current||'';
  $('delete-queue-run').disabled=doing||!waiting.length;$('delete-queue-run').textContent='Run '+waiting.length+' deletion'+(waiting.length===1?'':'s');$('delete-queue-pause').disabled=!doing;$('delete-queue-stop').disabled=!doing;
  $('delete-queue-follow').hidden=follow;updateBookmarks();
 }
 async function poll(){if(polling)return;polling=true;try{state=await api('/api/delete-queue');renderQueue();}catch(e){$('delete-queue-connection').textContent=e.message;}finally{polling=false;clearTimeout(pollTimer);pollTimer=setTimeout(poll,document.hidden?30000:active()||$('delete-queue-dialog').open?2000:15000);}}
 async function showQueue(){const d=$('delete-queue-dialog');if(!d.open)d.showModal();await poll();}
 async function queueAction(action){const b=$('delete-queue-'+(action==='run'?'run':action));b.disabled=true;try{state=await api('/api/delete-queue/action',{action,ids:pending().map(j=>j.id)});renderQueue();}finally{await poll();}}
 async function discover(){const b=$('native-discover');b.disabled=true;try{await api('/api/codex/discover',{});for(;;){const value=await api('/api/codex/status');$('native-status').textContent=(value.running?'Discovering native sessions… ':'Native Codex: ')+value.found+' available'+(value.errors.length?' · '+value.errors.join('; '):'');if(!value.running)break;await new Promise(r=>setTimeout(r,1500));}}finally{b.disabled=false;}}
 function init(){
  const bridgeStatus=el('span','connection-state');bridgeStatus.id='connection-state';bridgeStatus.setAttribute('role','status');bridgeStatus.append(el('span','connection-dot'),document.createTextNode('Disconnected'));const retry=el('button','','Reconnect');retry.id='connection-reconnect';retry.onclick=safeRun(reconnect);const group=el('span','connection-group');group.append(bridgeStatus,retry);$('message-stat').after(group);const remote=el('span','remote-chat-state');remote.id='remote-chat-state';remote.hidden=true;$('catalog-message-count').after(remote);
  const trash=$('trash-panel'),footer=el('div','collection-footer'),queue=el('button','delete-primary','Queue delete');queue.id='trash-queue-delete';queue.onclick=safeRun(()=>stage([...selected]));footer.append(queue);trash.append(footer);
  const current=el('button','','Move current chat to Trash');current.onclick=safeRun(async()=>{if(!S.selected)return;await organize(S.selected.id,{trashed:1});renderSidebar();renderTrash();});trash.insertBefore(current,$('trash-filter'));
  const p=el('section','collection-panel');p.id='bookmarks-panel';p.hidden=true;p.setAttribute('role','dialog');p.setAttribute('aria-label','Bookmarks');const head=el('div','trash-heading');head.append(el('h3','','Bookmarks'),button('Close Bookmarks','close',()=>{p.hidden=true;}));const toggle=el('button');toggle.id='bookmark-current';toggle.onclick=safeRun(async()=>{if(!S.selected)return;await organize(S.selected.id,{bookmarked:S.selected.bookmarked?0:1});updateBookmarks();});const search=el('input');search.id='bookmarks-filter';search.type='search';search.placeholder='Find a bookmarked chat';search.setAttribute('aria-label',search.placeholder);search.oninput=updateBookmarks;const list=el('div');list.id='bookmarks-list';p.append(head,toggle,search,list);document.body.append(p);
  const nav=el('button','nav-action trash-nav');nav.id='bookmarks-open';nav.append(ViewerIcons.svg('bookmark'),document.createTextNode('Bookmarks'),el('small'));nav.onclick=showBookmarks;$('trash-open').before(nav);
  const queueNav=el('button','delete-primary');queueNav.id='delete-queue-open';queueNav.hidden=true;queueNav.onclick=safeRun(showQueue);$('trash-open').after(queueNav);
  const toolbar=document.querySelector('.header-right');toolbar.insertBefore(button('Open Bookmarks','bookmark',showBookmarks),$('chat-menu'));toolbar.insertBefore(button('Open Trash','trash',()=>ChatControls.showTrash()),$('chat-menu'));
  $('delete-choice-add').onclick=safeRun(add);$('delete-queue-run').onclick=safeRun(()=>queueAction('run'));$('delete-queue-pause').onclick=safeRun(()=>queueAction('pause'));$('delete-queue-stop').onclick=safeRun(()=>queueAction('stop'));
  $('delete-queue-list').addEventListener('wheel',()=>{follow=false;$('delete-queue-follow').hidden=false;},{passive:true});$('delete-queue-list').addEventListener('pointerdown',()=>{follow=false;});$('delete-queue-follow').onclick=()=>{follow=true;lastActive='';renderQueue();};
  const setup=el('section','connection-setup-panel'),summary=el('strong','','Connect browser'),guide=el('p','queue-status','Use the bundled Browser connection extension with a signed-in ChatGPT tab. Load its folder once using your browser’s Load unpacked option, then refresh your ChatGPT tab. This folder is already paired to this viewer. No exporter is required.');
  const location=el('code','connection-folder'),copyPairing=el('button','','Copy pairing'),openFolder=el('button','','Open connection folder');
  let config=null;const loadSetup=async()=>config||=await api('/api/connection/setup');
  copyPairing.onclick=safeRun(async()=>{const c=await loadSetup();await navigator.clipboard.writeText(JSON.stringify({endpoint:c.endpoint,key:c.key}));toast('Pairing copied. Paste it into the Browser connection extension popup.');});
  openFolder.onclick=safeRun(async()=>{await api('/api/connection/open-folder',{});});
  setup.append(summary,guide,location,openFolder,copyPairing);setup.hidden=true;
  const exporter=el('details'),exporterSummary=el('summary','','Optional exporter handoff'),path=el('input');path.id='exporter-adapter-path';path.placeholder='Unpacked exporter extension folder';path.setAttribute('aria-label',path.placeholder);const pick=el('button','','Browse…');pick.onclick=safeRun(async()=>{const r=await api('/api/pick-folder',{path:path.value});if(r.path)path.value=r.path;});const install=el('button','','Enable handoff');install.onclick=safeRun(async()=>{install.disabled=true;try{const r=await api('/api/delete-queue/install-bridge',{path:path.value.trim()});toast(r.message);}finally{install.disabled=false;}});exporter.append(exporterSummary,path,pick,install,el('p','queue-status','Exporter 2.4.12 / 2.4.13. Reload the extension after installing the adapter. When its dashboard is active, it executes the same leased queue through its own scheduler.'));setup.append(exporter);$('delete-queue-dialog').insertBefore(setup,$('delete-queue-list'));
  const showSetup=async()=>{setup.hidden=false;location.textContent=(await loadSetup()).folder;};
  const setupToggle=el('button','','Connection setup');setupToggle.setAttribute('aria-expanded','false');setupToggle.onclick=safeRun(async()=>{setup.hidden=!setup.hidden;setupToggle.setAttribute('aria-expanded',String(!setup.hidden));if(!setup.hidden)await showSetup();});setup.before(setupToggle);
  const connectOpen=el('button','','Connect browser');connectOpen.id='connection-setup';connectOpen.onclick=safeRun(async()=>{await showQueue();await showSetup();setupToggle.setAttribute('aria-expanded','true');});group.append(connectOpen);
  const deleteCurrent=el('button','delete-primary','Queue deletion of current chat');deleteCurrent.onclick=safeRun(()=>S.selected&&stage([S.selected.id]));trash.insertBefore(deleteCurrent,$('trash-filter'));
  const native=el('section','native-discovery'),nativeButton=el('button','','Detect native Codex chats');nativeButton.id='native-discover';nativeButton.onclick=safeRun(discover);const status=el('p','muted');status.id='native-status';status.setAttribute('role','status');status.textContent='Uses CODEX_HOME or your Windows profile .codex folder. Session bodies load when opened.';const nativeToggle=el('label','check'),nativeCheck=el('input');nativeCheck.type='checkbox';nativeCheck.id='native-startup';nativeCheck.checked=S.settings.nativeCodexEnabled!==false;nativeCheck.onchange=safeRun(()=>saveSetting('nativeCodexEnabled',nativeCheck.checked));nativeToggle.append(nativeCheck,document.createTextNode('Discover native Codex at startup'));native.append(nativeButton,nativeToggle,status);$('folder-dialog').append(native);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')p.hidden=true;});window.addEventListener('resize',()=>{if(!p.hidden)place(p);});document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});updateBookmarks();poll();
 }
 document.addEventListener('DOMContentLoaded',init);return {renderTrash,updateBookmarks,showBookmarks,showQueue,stage,remoteHeader,connection};
})();
