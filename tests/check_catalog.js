const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={window:{},Intl,Date};vm.createContext(context);for(const name of ['catalog-model.js','organization.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',name),'utf8'),context);
const model=context.window.CatalogModel,order=context.window.SidebarOrder,title=c=>c.alias||c.title,kind=c=>c.kind;
const time=value=>model.dayBoundary(value),chats=[
 {id:'a',title:'Original café',alias:'Renamed report',project:'Energy',category:'Research',kind:'work',created:time('2024-12-04'),updated:time('2025-01-05'),pinned:1,position:10},
 {id:'b',title:'New chat',kind:'chat',created:time('2024-12-04')+86399,updated:time('2025-01-06'),category:'Research',position:20},
 {id:'c',title:'Third',kind:'work',created:time('2024-12-05'),updated:time('2025-01-06'),category:'Research',position:30},
 {id:'hidden',title:'Removed',trashed:1,kind:'chat'},
 {id:'unknown',title:'No date',kind:'chat'}
];const ids=rows=>Array.from(rows,c=>c.id),reads={a:{updated:chats[0].updated}};
assert.deepEqual(ids(model.filter(chats,{query:'CAFE research'},reads,title)),['a']);
assert.deepEqual(ids(model.filter(chats,{query:'original'},reads,title)),['a']);
assert.deepEqual(ids(model.filter(chats,{query:'Renamed energy'},reads,title)),['a']);
assert.deepEqual(ids(model.filter(chats,{read:'read',pinned:true,projects:'only'},reads,title)),['a']);
assert.deepEqual(ids(model.filter(chats,{read:'unread',projects:'none',untitled:true},reads,title)),['b']);
assert.deepEqual(ids(model.filter(chats,{field:'created',from:'2024-12-04',to:'2024-12-04'},reads,title)),['a','b']);
assert.deepEqual(ids(model.filter(chats,{from:'2025-01-06',to:'2025-01-06'},reads,title)),['b','c']);
assert.equal(model.dayBoundary('2025-02-30'),null);assert.equal(model.dayBoundary('invalid'),null);
assert(!model.isRead({...chats[0],updated:chats[0].updated+1},reads));assert(model.isRead(chats[0],reads));
const settings={groupOrder:{categories:['pinned','category:Research']},groupSort:{'categories|category:Research':'manual'}};
const snapshot=JSON.stringify([chats,settings]);const groups=order.groups(model.filter(chats,{},reads,title),settings,'work','categories',true,kind,title,'oldest');
assert.deepEqual(Array.from(groups.keys()),['pinned','category:Research']);assert.deepEqual(ids(groups.get('pinned')),['a']);assert.deepEqual(ids(groups.get('category:Research')),['c']);
order.groups(model.filter(chats,{query:'third'},reads,title),settings,'work','categories',true,kind,title,'title');assert.equal(JSON.stringify([chats,settings]),snapshot);


assert(order.compare(chats[0],chats[2],'title-desc',title)>0);assert(order.compare(chats[0],chats[2],'updated-oldest',title)<0);

console.log('Catalog combined filters, inclusive date boundaries, read revisions, original-title search and layered order checks passed.');
