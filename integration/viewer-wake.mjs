// Browser-owned wake-up only. All authenticated HTTP remains in the locked dashboard.
import * as db from './storage.mjs';
import {pending,readQueue} from './viewer-delete-adapter.mjs';
export async function wake(api=chrome,store=db){
 const scope=await store.get('meta','lastScope');if(!scope?.key)return;
 const folder=await store.get('meta',`folder:${scope.key}`);if(!folder)return;
 if(await folder.queryPermission({mode:'readwrite'})!=='granted')return;
 const reset=await readQueue(folder,'.viewer-queue/reconnect.json');
 const connection=await store.get('meta',`viewerConnection:${scope.key}`);
 if(connection?.blocked&&connection.nonce!==(reset?.nonce||''))await store.put('meta',`viewerConnection:${scope.key}`,{nonce:reset?.nonce||'',attempts:0,blocked:false});
 else if(connection?.blocked)return;
 if(!await pending(folder,scope.key)&&(!reset?.nonce||connection?.nonce===reset.nonce))return;
 const url=api.runtime.getURL('exporter.html');
 const tabs=await api.tabs.query({url:url+'*'});if(tabs.length)return;
 // The dashboard's existing navigator.locks lease decides ownership, even on races.
 await api.tabs.create({url:url+'?viewerQueue=1',active:false});
}
