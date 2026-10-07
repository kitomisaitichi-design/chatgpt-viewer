// A lock-losing page may become the owner after the previous dashboard closes.
// No folder, account or network work happens until the exclusive lock is held.
export function own({locks,ready,blocked,error,schedule=setInterval,unschedule=clearInterval}){
 let claiming=false,started=false;
 async function claim(){
  if(claiming||started)return;
  claiming=true;
  try{
   await locks.request('english-exporter-dashboard',{ifAvailable:true},async lock=>{
    if(!lock){blocked();return;}
    started=true;await ready();await new Promise(()=>{});
   });
  }catch(e){error(e);}finally{claiming=false;}
 }
 const timer=schedule(()=>void claim(),10000);void claim();
 return ()=>unschedule(timer);
}
