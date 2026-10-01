'use strict';
// Folder controls work before the archive request or optional renderers finish.
(()=>{
 const byId=id=>document.getElementById(id);
 for(const id of ['welcome-folder','scan-open']){const b=byId(id);if(b)b.onclick=()=>byId('folder-dialog').showModal();}
 document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
 window.viewerBootTime=performance.now();
 setTimeout(()=>{if(!window.viewerAppStarted){byId('startup-note').hidden=false;byId('startup-note').textContent='The reader did not initialize. Restart START-VIEWER.bat from the fully extracted update. Folder settings can still be opened.';}},5000);
})();
