/*
 * Browser-only, non-destructive v1.1.28 frontend race regression fixture.
 *
 * Start a static read-only server from the project root:
 *   runtime\python.exe -u -m http.server 0 --bind 127.0.0.1 --directory web
 * Open a NEW isolated background browser tab at
 *   http://127.0.0.1:<printed-port>/__frontend-race-fixture__
 * (the 404 page is intentional). Paste this entire JS expression into that
 * tab's developer console, or evaluate it through the Desktop browser tool.
 * The expression returns a Promise of self-contained JSON results, also saved
 * on window.__frontendRaceResults. It does not access a live viewer server,
 * original archive, account data, or application settings.
 *
 * The authentic app.js auto-start call is omitted only in the disposable
 * browser compilation; its functions otherwise execute unchanged. Real
 * find.js, viewer-controls.js, reader.js, thread-images.js and
 * thread-attachments.js are executed; only API responses, DOM dependencies,
 * optional rendering workers, and IntersectionObserver scheduling are faked.
 *
 * Requires a modern browser and the web/ assets available via this origin.
 */
(async function verifyFrontendRacesV1128() {
  'use strict';
  const results = [];
  window.__frontendRaceProgress = results;
  const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const $ = id => document.getElementById(id);
  const note = (test, facts) => results.push({test, ...facts});
  const assert = (truth, explanation) => {if (!truth) throw Error(explanation);};
  const record = async (test, fn) => {
    try { note(test, await fn()); }
    catch (error) { note(test, {pass:false, error:error.message, evidence:'EXECUTED/ERROR'}); }
  };
  const source = async name => {
    const response = await fetch('/' + name);
    if (!response.ok) throw Error('Test fixture must serve web/' + name);
    return response.text();
  };
  const elementIds = [
    'messages','welcome','conversation','end-card','bottom-loader','chat-title',
    'kind-pill','load-older','load-info','scroller','message-stat','continue',
    'details-toggle','pin-chat','end-meta','search-results','search-summary',
    'search-meta','search-query','search-mode','search-type','search-category',
    'search-sort','inchat-query','inchat-bar','archive-return','inchat-count',
    'toast','settings-dialog'
  ];
  document.body.replaceChildren(...elementIds.map(id => {
    const node = document.createElement('div'); node.id = id; return node;
  }));
  $('scroller').append($('messages'));
  window.toast = () => {};
  window.ViewerIcons = {
    set(){},
    svg(){return document.createElement('span');}
  };
  window.Reader = {
    cancel(){}, closeTable(){}, foldState(){}, typeset(){}, release(){},
    resume(){}, prioritize(){},
    create(m){const div=document.createElement('div');div.textContent=m.text;return div;},
    ensure(){return Promise.resolve();},
    fullText(m){return Promise.resolve(m.text);}
  };
  window.ThreadAttachments = {close(){},mount(){},release(){},resume(){},catalog(){return Promise.resolve({attachments:[]});}};
  window.ThreadImages = {close(){},mount(){},release(){},resume(){},bindRendered(){},cleanReferences(){}};
  window.CatalogControls = {header(){},opened(){},sync(){}};
  window.ChatControls = {update(){}};
  window.Collections = {connection(){}};

  let pending = [],deferOlderPage=false,fragmentHashFailure=false;
  const fragmentPaths=[];
  let sourceRevision = 'F1';
  const serverSettings = {};
  const deferred = (kind, path, data, options) => new Promise((resolve, reject) => {
    pending.push({kind, path, data, options, resolve, reject, done:false});
  });
  const waiting = kind => pending.filter(request => request.kind === kind && !request.done);
  const reply = (kind, index, value = {}) => {
    const request = waiting(kind)[index];
    if (!request) throw Error('Expected outstanding ' + kind + ' request ' + index);
    request.done = true;
    if (kind === 'settings') Object.assign(serverSettings, request.data);
    request.resolve(value);
    return request;
  };
  const clear = kind => {pending = pending.filter(request => request.kind !== kind);};
  window.__raceApi = (path, data, options = {}) => {
    if(path.startsWith('/api/message-text?')){
      fragmentPaths.push(path);
      if(fragmentHashFailure)return Promise.reject(Error('Message hash mismatch; source changed'));
      return Promise.resolve({text:'-END',next_offset:9,complete:true});
    }
    if (path.startsWith('/api/messages')) {
      const query = new URL(path, location.href).searchParams;
      if(deferOlderPage&&query.has('before'))return deferred('pages',path,data,options);
      const cid = query.get('id'), leaf = query.get('leaf') || 'main';
      return Promise.resolve({
        messages:[{role:'assistant',seq:0,visible:true,text:cid+'-'+leaf+'-'+sourceRevision,extras:{}}],
        older:0,newer:0,total:1
      });
    }
    for (const [prefix,kind] of [
      ['/api/settings','settings'], ['/api/find?','find'], ['/api/search?','search'],
      ['/api/thread-images?','images'], ['/api/thread-attachments?','attachments']
    ]) if (path.startsWith(prefix)) return deferred(kind,path,data,options);
    return Promise.resolve({});
  };
  const appText = await source('app.js');
  const cut = appText.indexOf('\nstart();');
  assert(cut > 0, 'Expected app.js startup call to isolate');
  new Function(appText.slice(0, cut) + '\n' +
    'api=window.__raceApi;loadReaders=()=>{};' +
    'window.__app={S,openChat,mergeCatalog,rememberChat,search,loadPage,renderMessage};' +
    'window.S=S;window.openChat=openChat;window.api=api;' +
    'window.saveSetting=saveSetting;window.applyAppearance=applyAppearance;')();
  const app = window.__app, S = app.S;
  for (const id of ['c','other']) S.chatById.set(id, {
    id,title:id,fingerprint:id==='c'?'F1':'O1',created:100,updated:100
  });
  S.chats = [...S.chatById.values()];
  S.settings = {pageSize:100};

  await record('selected source F1 -> F2 auto-reload and warm-cache coherency', async () => {
    await app.openChat('c');
    const first = {fingerprint:S.selected.fingerprint,text:S.messages[0].text};
    sourceRevision='F2';
    app.mergeCatalog([{id:'c',title:'c',fingerprint:'F2',created:100,updated:101}]);
    await wait(60);
    const refreshed={fingerprint:S.selected.fingerprint,text:S.messages[0].text};
    await app.openChat('other');
    await app.openChat('c');
    const final={fingerprint:S.selected.fingerprint,text:S.messages[0].text};
    return {pass:first.text==='c-main-F1'&&refreshed.fingerprint==='F2'&&
      refreshed.text==='c-main-F2'&&final.fingerprint==='F2'&&final.text==='c-main-F2',
      interpretation:'PASS: active reader auto-reloads F2 and warm cache preserves F2',
      first,refreshed,final,evidence:'EXECUTED app.js:51,100-102,113-134'};
  });

  await record('delayed older page cannot mix previous fingerprint messages',async()=>{
    clear('pages');
    await app.openChat('c',null,true,'A');
    S.older=1;
    deferOlderPage=true;
    const oldPage=app.loadPage('older');
    assert(waiting('pages').length===1,'Expected pending page from F2');
    sourceRevision='F3';
    app.mergeCatalog([{id:'c',title:'c',fingerprint:'F3',created:100,updated:102}]);
    reply('pages',0,{messages:[{role:'assistant',seq:-1,visible:true,text:'c-A-F2-stale-page',extras:{}}],
      older:0,newer:0,total:2});
    await oldPage;
    deferOlderPage=false;
    await wait(60);
    const messages=S.messages.map(m=>m.text),dom=$('messages').textContent;
    return {pass:S.selected.fingerprint==='F3'&&
      messages.length===1&&messages.every(text=>text.endsWith('-F3'))&&!dom.includes('F2-stale-page'),
      fingerprint:S.selected.fingerprint,messages,stalePageInDom:dom.includes('F2-stale-page'),
      interpretation:'PASS: source revision invalidates in-flight older page and rerenders F3',
      evidence:'EXECUTED app.js:51,113-142'};
  });

  new Function(await source('find.js'))();
  await record('Find leaf A response after selecting leaf B', async () => {
    window.ArchiveFind.close(); clear('find');
    $('inchat-query').value='needle';
    await app.openChat('c',null,true,'A');
    const task=ArchiveFind.find();
    assert(waiting('find').length===1,'Find did not issue /api/find');
    await app.openChat('c',null,true,'B');
    const before={leaf:S.leaf,text:S.messages[0].text};
    reply('find',0,{results:[{seq:0}],truncated:false});
    await task;
    const after={leaf:S.leaf,text:S.messages[0].text};
    ArchiveFind.close();
    return {pass:before.leaf==='B'&&after.leaf==='B'&&after.text===before.text,
      interpretation:'PASS: stale A Find cannot restore A after selecting B',
      before,after,evidence:'EXECUTED find.js:16-25, app.js:113-134'};
  });

  new Function(await source('viewer-controls.js'))();
  await record('concurrent light then black theme writes', async () => {
    clear('settings');S.settings.theme='dark';S.settings.lastDarkTheme='dark';
    serverSettings.theme='dark';serverSettings.lastDarkTheme='dark';
    const older=ViewerControls.theme('light'),newer=ViewerControls.theme('black');
    const initial=waiting('settings').map(r=>r.data);
    assert(initial.length===2,'Expected simultaneous theme saves');
    const immediately={local:S.settings.theme,durable:serverSettings.theme};
    assert(immediately.local==='black','Latest theme intent was not applied immediately');
    // Deliberately complete the old Light writes after Black was requested.
    // Per-key sequencing must submit the queued Black writes only afterwards.
    reply('settings',1);
    reply('settings',0);
    await wait(0);
    const queued=waiting('settings').map(r=>r.data);
    assert(queued.length===2&&queued.some(x=>x.theme==='black')&&
      queued.some(x=>x.lastDarkTheme==='black'),'Black writes must follow old Light saves');
    await older;
    reply('settings',1);
    reply('settings',0);
    await newer;
    const final={local:S.settings.theme,durable:serverSettings.theme,lastDarkTheme:serverSettings.lastDarkTheme};
    return {pass:final.local==='black'&&final.durable==='black'&&final.lastDarkTheme==='black',
      interpretation:'PASS: writes for each key commit in intent order; Black persists after delayed Light',
      initial,immediately,queued,final,evidence:'EXECUTED viewer-controls.js:4, app.js:20'};
  });

  await record('overlapping archive search keeps newest', async () => {
    clear('search');
    for (const [id,value] of [
      ['search-mode','smart'],['search-type','all'],
      ['search-category','all'],['search-sort','recent']
    ]) $(id).value=value;
    $('search-query').value='first';const older=app.search();
    $('search-query').value='second';const newer=app.search();
    const queries=waiting('search').map(x=>new URL(x.path,location.href).searchParams.get('q'));
    reply('search',1,{mode:'smart',results:[{
      cid:'c',seq:0,role:'assistant',snippet:'second matched',matched_text:'second'
    }]});
    await newer;
    const afterNewer=$('search-results').textContent;
    reply('search',0,{mode:'smart',results:[{
      cid:'other',seq:0,role:'assistant',snippet:'first matched',matched_text:'first'
    }]});
    await older;
    const final=$('search-results').textContent;
    return {pass:queries.join(',')==='first,second'&&afterNewer===final&&
      final.includes('second matched')&&!final.includes('first matched'),
      interpretation:'PASS: app.js generation discards stale archive-search response even with mock ignoring abort',
      queries,afterNewer,final,evidence:'EXECUTED app.js:157'};
  });

  const observers=[];
  class FixtureObserver {
    constructor(callback,options){this.callback=callback;this.options=options||{};this.nodes=new Set();observers.push(this);}
    observe(node){this.nodes.add(node);}
    unobserve(node){this.nodes.delete(node);}
    disconnect(){this.nodes.clear();}
    fire(node){this.callback([{target:node,isIntersecting:true}],this);}
  }
  window.IntersectionObserver=FixtureObserver;
  class FixtureWorker {
    constructor(name){this.name=name;setTimeout(()=>this.onmessage?.({data:{ready:true}}),0);}
    postMessage(job){setTimeout(()=>this.onmessage?.({data:{
      id:job.id,html:'<p>'+String(job.text||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</p>'
    }}),20);}
    terminate(){}
  }
  window.Worker=FixtureWorker;
  window.RichMedia={blocks:x=>x,markup:x=>x,combine:(text,widgets)=>({text,widgets})};
  window.SavedWidgets={extract:text=>({text,widgets:[]}),render:()=>document.createElement('span')};
  window.DocumentCards={extract:text=>({text,documents:[]}),decorate(){}};
  window.CodePresentation={readable:()=>false};
  new Function(await source('reader.js'))();
  await record('native link decorator integration hooks for user and assistant',async()=>{
    const calls=[];
    window.NativeFileLinks={decorate(root){calls.push(root.nodeType);}};
    const user=app.renderMessage({role:'user',visible:true,seq:991,text:'Saved file example.txt',extras:{}});
    $('messages').append(user);
    const wrapper=document.createElement('article');
    const assistantRoot=Reader.create({role:'assistant',visible:true,seq:992,text:'Saved file example.txt',extras:{}},'c','c|B|992');
    wrapper.append(assistantRoot);$('messages').append(wrapper);
    const observer=observers.find(o=>o.options.rootMargin==='800px');
    observer.fire(assistantRoot);await wait(90);
    Reader.release([user,wrapper]);user.remove();wrapper.remove();
    return {pass:calls.length>=2&&calls.every(type=>type===1),
      decoratedHostNodeTypes:calls,
      interpretation:'PASS: app.js hands user body and reader.js hands sanitized assistant DOM to NativeFileLinks.decorate',
      evidence:'EXECUTED app.js:94 and reader.js:108; decorator is test stub, link parsing is prime-owned'};
  });
  await record('fragment hash mismatch does not stitch changed source text',async()=>{
    fragmentHashFailure=true;
    const m={seq:3,text:'BEGIN',text_complete:false,text_next:5,text_hash:'fixture-sha256'};
    let error='';
    try{await Reader.fullText(m,'c',S.leaf);}catch(e){error=e.message;}
    fragmentHashFailure=false;
    const query=new URL(fragmentPaths.at(-1),location.href).searchParams;
    return {pass:query.get('hash')==='fixture-sha256'&&m.text==='BEGIN'&&m.text_next===5&&
      m.text_complete===false&&error.includes('Reopen the conversation'),
      hashSent:query.get('hash'),textAfterFailure:m.text,offset:m.text_next,
      error,interpretation:'PASS: source hash supplied, mismatching chunk rejected without text mutation',
      evidence:'EXECUTED reader.js:104'};
  });
  await record('lazy viewport formatting and detached-root guard',async()=>{
    const message={role:'assistant',seq:9,text:'lazy marker',extras:{}};
    const wrap=document.createElement('article'),root=Reader.create(message,'c','c|A|9');
    wrap.append(root);$('messages').append(wrap);
    const observer=observers.find(o=>o.options.rootMargin==='800px');
    assert(observer?.nodes.has(root),'Reader.create did not schedule IntersectionObserver');
    const before=!!root.dataset.formatted;
    observer.fire(root);await wait(100);
    const formatted=!!root.dataset.formatted;
    Reader.release([wrap]);const released=!observer.nodes.has(root);
    const second=document.createElement('article'),gone=Reader.create({role:'assistant',seq:10,text:'removed marker',extras:{}},'c','c|A|10');
    second.append(gone);$('messages').append(second);
    observer.fire(gone);gone.remove();await wait(100);
    const detachedSkipped=!gone.dataset.formatted;
    Reader.release([second]);
    return {pass:!before&&formatted&&released&&detachedSkipped,
      before,formatted,released,detachedSkipped,
      interpretation:'PASS: actual Reader observer schedules lazy format; detached root cannot commit',
      evidence:'EXECUTED reader.js:27-33,103-125; FakeWorker returns HTML'};
  });

  new Function(await source('thread-images.js'))();
  new Function(await source('thread-attachments.js'))();
  await record('delayed image/attachment catalogs after branch switch',async()=>{
    clear('images');clear('attachments');
    S.selected=S.chatById.get('c');S.leaf='A';
    const art=document.createElement('article'),body=document.createElement('div');
    body.className='message-body';art.append(body);$('messages').append(art);
    const message={seq:0,text:'asset probe',extras:{}};
    ThreadImages.mount(art,message,'c','A');
    ThreadAttachments.mount(art,message,'c','A');
    const img=art.querySelector('.message-images'),att=art.querySelector('.message-attachments');
    for(const observer of observers.filter(o=>o.options.rootMargin==='500px')) {
      if(observer.nodes.has(img))observer.fire(img);
      if(observer.nodes.has(att))observer.fire(att);
    }
    assert(waiting('images').length===1&&waiting('attachments').length===1,'Catalog requests were not queued');
    S.leaf='B';
    reply('images',0,{images:[{id:'i1',name:'a.png',seq:0,sequences:[0],references:['a.png'],available:true}],last_seq:0,revision:'r1'});
    reply('attachments',0,{attachments:[{id:'d1',kind:'markdown',name:'a.md',seq:0,sequences:[0],references:['a.md'],available:true,size:8}],last_seq:0,revision:'r1'});
    await wait(20);
    const ignored={images:img.children.length,attachments:att.children.length};
    S.leaf='A';
    const again=document.createElement('article'),againBody=document.createElement('div');
    againBody.className='message-body';again.append(againBody);$('messages').append(again);
    ThreadImages.mount(again,message,'c','A');
    ThreadAttachments.mount(again,message,'c','A');
    for(const observer of observers.filter(o=>o.options.rootMargin==='500px')) {
      const i=again.querySelector('.message-images'),a=again.querySelector('.message-attachments');
      if(observer.nodes.has(i))observer.fire(i);
      if(observer.nodes.has(a))observer.fire(a);
    }
    await wait(20);
    const restored={images:again.querySelectorAll('.image-thumbnail').length,
      attachments:again.querySelectorAll('.attachment-card').length};
    return {pass:ignored.images===0&&ignored.attachments===0&&
      restored.images===1&&restored.attachments===1,
      ignored,restored,interpretation:'PASS: lazy catalogs reject old branch, current branch renders assets',
      evidence:'EXECUTED thread-images.js:7,25-27 and thread-attachments.js:7,62-64'};
  });
  window.__frontendRaceResults=results;
  return results;
})()
