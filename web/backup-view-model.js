'use strict';
window.BackupViewModel=(()=>{
 function bytes(value){let n=Number(value)||0;for(const unit of ['B','KB','MB','GB','TB']){if(n<1024||unit==='TB')return (unit==='B'?Math.round(n):n.toFixed(n<10?2:1))+' '+unit;n/=1024;}}
 function state(data){
  const files=Object.values(data.files||{}),broken=data.needs_rebuild||files.some(f=>['changed','missing'].includes(f.integrity));
  const error=data.progress?.error||data.retry_error||'';
  return {busy:data.running===true,broken,error,approval:!!data.needs_delivery_approval,local:broken?'Needs rebuild':files.some(f=>f.verified)?'Verified ZIP available':files.some(f=>f.exists)?'Verification needed':'No completed ZIP',delivery:data.delivery_pending?(broken?'Rebuild before delivery':data.needs_delivery_approval?'Review rebuilt ZIPs':data.retry_paused?'Paused':error?'Retry needed':'Pending'):data.last_success?(data.config?.route==='desktop'?'Folder copy completed':'Upload confirmed'):'No delivery yet'};
 }
 function progress(p){if(!p.total)return '';const percent=Math.min(100,Math.round(p.done/p.total*100));return percent+'%'+(/^(Packaging|Uploading|Copying)/.test(p.phase||'')?' · '+bytes(p.done)+' / '+bytes(p.total):/^(Capturing selected chats|Integrating conversations)/.test(p.phase||'')?' · '+p.done+' / '+p.total+' chats':'');}
 return {bytes,state,progress};
})();
