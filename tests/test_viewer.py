import gzip, http.client, json, sys, tempfile, threading, unittest, time
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from viewer import Archive, Server, VERSION, parse_json, parse_md

def fixture(cid='12345678-abcd-1234-abcd-123456789012',n=230):
    mapping={'root':{'parent':None,'children':['n0'],'message':None}}
    for i in range(n):
        text=f'Message {i}: '+('Electricity shortage and the cost of fuel.' if i%2 else 'How do I search my archived conversations?')
        if i==n-1:text='## A readable archive\n\nHere is a table.\n\n| View | Behavior |\n|---|---|\n| Latest | Loads 100 messages |\n| Earlier | Scroll up |\n\n```python\nprint("hello")\n```\n\nMath: \\(E=mc^2\\)\n\n![local image](sample.png)'
        mapping['n'+str(i)]={'parent':'n'+str(i-1) if i else 'root','children':['n'+str(i+1)] if i<n-1 else [],'message':{'author':{'role':'user' if i%2==0 else 'assistant'},'create_time':1700000000+i,'content':{'content_type':'text','parts':[text]},'metadata':{}}}
    return {'conversation_id':cid,'title':'Archive example: long conversation','create_time':1700000000,'update_time':1700000500,'mapping':mapping,'current_node':'n'+str(n-1)}

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.exports=self.base/'parent'/'exports';self.exports.mkdir(parents=True);self.a=Archive(self.base/'data',background_process=False)
    def tearDown(self):self.a.close();self.tmp.cleanup()
    def write(self,relative,obj):
        f=self.exports/relative;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(obj) if not isinstance(obj,str) else obj,encoding='utf-8');return f
    def test_branch_follows_selected_path_not_all_messages(self):
        x=fixture(n=4);x['mapping']['alt']={'parent':'n1','children':[],'message':{'author':{'role':'assistant'},'content':{'parts':['Other branch']}}};x['current_node']='alt'
        p=parse_json(x,self.exports/'chat.json');self.assertEqual(len(p['messages']),3);self.assertEqual(p['messages'][-1]['text'],'Other branch')
    def test_model_metadata_receipt_preserves_served_effort_and_reroute(self):
        x=fixture(n=2);x['mapping']['n1']['message']['metadata']={'model_slug':'intermediate','resolved_model_slug':'served','default_model_slug':'picked','requested_model_slug':'router','thinking_effort':'extended'}
        m=parse_json(x,self.exports/'chat.json')['messages'][1];r=m['extras']['receipt'];self.assertEqual(r['served'],'served');self.assertEqual(r['effort'],'extended');self.assertTrue(r['rerouted']);self.assertEqual(r['raw']['requested_model_slug'],'router')
        x['mapping']['n1']['message']['metadata']['default_model_slug']='gpt-auto';self.assertFalse(parse_json(x,self.exports/'chat.json')['messages'][1]['extras']['receipt']['rerouted'])
    def test_regenerated_reply_versions_follow_branch(self):
        x=fixture(n=4);x['mapping']['alt']={'parent':'n0','children':[],'message':{'author':{'role':'assistant'},'content':{'content_type':'text','parts':['Regenerated answer']},'create_time':1700000600}}
        self.write('chat.json',x);self.a.scan(self.exports,0);cid=x['conversation_id'];messages=self.a.page(cid)['messages'];self.assertEqual(messages[1]['extras']['versions'],['n1','alt'])
        leaf=self.a.choose_version(cid,'alt');self.assertEqual(leaf,'alt');p=self.a.branch_page(cid,leaf);self.assertEqual(len(p['messages']),2);self.assertEqual(p['messages'][-1]['text'],'Regenerated answer')
    def test_edited_user_versions_and_no_false_continuation_versions(self):
        x=fixture(n=4);x['mapping']['edit']={'parent':'root','children':[],'message':{'author':{'role':'user'},'content':{'parts':['Edited question']},'create_time':1700000600}}
        parsed=parse_json(x,self.exports/'chat.json');self.assertEqual(parsed['messages'][0]['extras']['versions'],['n0','edit']);self.assertEqual(parsed['messages'][3]['extras']['versions'],[])
    def test_branch_selection_in_standard_conversation_array(self):
        x=fixture(n=3);self.write('conversations.json',[x]);self.a.scan(self.exports,0);d,path=self.a.source_data(x['conversation_id']);self.assertEqual(d['title'],x['title']);self.assertEqual(self.a.choose_version(x['conversation_id'],'n0'),'n2')
    def test_mapping_cycle_terminates(self):
        x=fixture(n=2);x['mapping']['n0']['parent']='n1';self.assertEqual(len(parse_json(x,self.exports/'chat.json')['messages']),2)
    def test_markdown_role_inside_fence_is_not_message(self):
        f=self.write('readable.md','# Title\nConversation: https://chatgpt.com/c/abcdefgh123\n\n## You\nQuestion\n\n## Assistant\n```md\n## You\ncode\n```\nAnswer')
        p=parse_md(f.read_text(),f);self.assertEqual(len(p['messages']),2);self.assertIn('## You',p['messages'][1]['text']);self.assertEqual(p['id'],'abcdefgh123')
    def test_json_wins_over_markdown_and_metadata_enriches(self):
        x=fixture(n=6);self.write('json/chat.json',x);self.write('markdown/chat.md','# Same\nConversation: https://chatgpt.com/c/'+x['conversation_id']+'\n## You\nMD only')
        self.write('conversation-index.json',{'entries':[{'id':x['conversation_id'],'chat_kind':'work','project':'Research','create_time':1600000000}]})
        self.a.scan(self.exports,0);cs=self.a.catalog();self.assertEqual(len(cs),1);self.assertEqual(cs[0]['count'],6);self.assertEqual(cs[0]['kind'],'work');self.assertEqual(cs[0]['project'],'Research');self.assertEqual(cs[0]['created'],1600000000)
    def test_discovery_two_up_and_down(self):
        self.write('archive.json',fixture(n=2));child=self.exports/'nested'/'viewer';child.mkdir(parents=True);self.a.scan(child,2);self.assertEqual(len(self.a.catalog()),1)
    def test_tools_hidden_but_preserved(self):
        x=fixture(n=5);x['mapping']['n1']['message']['author']['role']='tool';x['mapping']['n3']['message']['channel']='analysis';self.write('chat.json',x);self.a.scan(self.exports,0);cid=x['conversation_id'];self.assertEqual(self.a.page(cid)['total'],3);self.assertEqual(self.a.page(cid,details=True)['total'],5)
    def test_paging_before_after_and_search_jump(self):
        x=fixture(n=350);self.write('chat.json',x);self.a.scan(self.exports,0);cid=x['conversation_id'];last=self.a.page(cid);self.assertEqual(last['first'],250);self.assertEqual(last['older'],250);self.assertEqual(len(last['messages']),100)
        prior=self.a.page(cid,before=250);self.assertEqual(prior['first'],150);self.assertEqual(prior['newer'],100)
        nextpage=self.a.page(cid,after=249);self.assertEqual(nextpage['first'],250)
        around=self.a.page(cid,around=70);self.assertTrue(any(m['seq']==70 for m in around['messages']))
    def test_search_contents_not_repeated_title(self):
        x=fixture(n=12);self.write('chat.json',x);self.a.scan(self.exports,0)
        rows=self.a.search('electricity shortage','keyword')['results'];self.assertTrue(rows);self.assertIn('Electricity',rows[0]['snippet'])
        self.assertTrue(self.a.search('fuel','keyword')['results']);self.assertTrue(self.a.search('energy','smart')['results']);self.assertTrue(self.a.search(x['conversation_id'])['results'])
        titles=self.a.search('long conversation','keyword')['results'];self.assertTrue(titles);self.assertEqual(titles[0]['seq'],-1)
    def test_search_can_be_restricted_to_chat(self):
        x=fixture(n=8);self.write('chat.json',x);self.a.scan(self.exports,0)
        self.assertTrue(self.a.search('electricity','keyword',x['conversation_id'])['results']);self.assertFalse(self.a.search('electricity','keyword','no-such-chat')['results'])
    def test_incremental_scan_and_changed_source(self):
        x=fixture(n=3);self.write('chat.json',x);self.a.scan(self.exports,0);self.a.scan(self.exports,0);self.assertEqual(self.a.status['indexed'],0)
        self.write('chat.json',fixture(n=8));self.a.scan(self.exports,0);self.assertEqual(self.a.catalog()[0]['count'],8)
    def test_organization_survives_reindex(self):
        x=fixture(n=2);self.write('chat.json',x);self.a.scan(self.exports,0);self.a.organize(x['conversation_id'],{'category':'Saved','pinned':1,'position':15,'alias':'Favorite'});self.a.save_settings({'theme':'black'});self.write('chat.json',fixture(n=4));self.a.scan(self.exports,0)
        c=self.a.catalog()[0];self.assertEqual(c['alias'],'Favorite');self.assertEqual(c['category'],'Saved');self.assertEqual(self.a.settings()['theme'],'black')
    def test_assets_within_root_and_traversal_rejected(self):
        x=fixture(n=2);self.write('chat.json',x);f=self.write('assets/test.txt','hello');self.a.scan(self.exports,0);self.assertEqual(self.a.asset(x['conversation_id'],'assets/test.txt'),f)
        outside=self.base/'secret.txt';outside.write_text('private')
        with self.assertRaises(FileNotFoundError):self.a.asset(x['conversation_id'],'../../secret.txt')
        with self.assertRaises(ValueError):self.a.asset(x['conversation_id'],'https://example.com/file')
    def test_conversation_array_and_portable_state_metadata(self):
        x=fixture(n=2);y=fixture('abcdefgh-second',n=3);self.write('conversations.json',[x,y]);self.write('portable-state.json',{'job':{'entries':{y['conversation_id']:{'id':y['conversation_id'],'chatKind':'codex','project':'Tools'}}}});self.a.scan(self.exports,0);self.assertEqual(len(self.a.catalog()),2);self.assertEqual(next(c for c in self.a.catalog() if c['id']==y['conversation_id'])['kind'],'codex')
    def test_unrelated_markdown_and_index_only_not_chats(self):
        self.write('README.md','# ordinary document\nNo chat role delimiters.');self.write('conversation-index.json',{'entries':[{'id':'abcdefgh123','title':'Not downloaded'}]});self.a.scan(self.exports,0);self.assertEqual(self.a.catalog(),[])
    def test_semantic_without_model_reports_text_fallback(self):
        x=fixture(n=4);self.write('chat.json',x);self.a.scan(self.exports,0)
        with patch.object(self.a,'request_semantic'):r=self.a.search('fuel','semantic')
        self.assertIn('notice',r);self.assertTrue(r['results'])

class ProgressiveScanTests(unittest.TestCase):
    setUp=ArchiveTests.setUp
    tearDown=ArchiveTests.tearDown
    write=ArchiveTests.write
    def test_first_chat_available_before_discovery_finishes(self):
        first=self.write('first.json',fixture('first-progressive',n=3));second=self.write('second.json',fixture('second-progressive',n=3));release=threading.Event()
        def discovery(start,root,event):
            yield first
            while not release.wait(.01) and not event.is_set():pass
            if not event.is_set():yield second
        with patch.object(self.a,'discover_paths',side_effect=discovery):
            self.a.request_scan(self.exports,0)
            deadline=time.monotonic()+3
            while len(self.a.catalog())<1 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(len(self.a.catalog()),1);self.assertTrue(self.a.status['scanning'])
            self.assertEqual(self.a.page('first-progressive')['total'],3)
            self.a.stop_scan();release.set()
            with self.a.scan_lock:pass
    def test_new_folder_replaces_running_scan(self):
        first=self.write('first.json',fixture('first-old-folder',n=3));newfolder=self.base/'new';newfolder.mkdir();newfile=newfolder/'new.json';newfile.write_text(json.dumps(fixture('new-folder-chat',n=4)))
        original=self.a.discover_paths
        def discovery(start,root,event):
            if start==self.exports.resolve():
                yield first
                while not event.wait(.01):pass
            else:yield from original(start,root,event)
        with patch.object(self.a,'discover_paths',side_effect=discovery):
            self.a.request_scan(self.exports,0);deadline=time.monotonic()+3
            while not self.a.catalog() and time.monotonic()<deadline:time.sleep(.01)
            self.a.request_scan(newfolder,0);deadline=time.monotonic()+3
            while not any(c['id']=='new-folder-chat' for c in self.a.catalog()) and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(any(c['id']=='new-folder-chat' for c in self.a.catalog()))
            while self.a.status['scanning'] and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(self.a.settings()['scan_start'],str(newfolder.resolve()));self.assertFalse(self.a.status['scanning'])
    def test_interrupted_array_resumes_remaining_conversations(self):
        self.write('conversations.json',[fixture('array-first',n=2),fixture('array-second',n=2)])
        original=self.a.store
        def store_and_stop(*args):
            original(*args);self.a.cancel_event.set()
        with patch.object(self.a,'store',side_effect=store_and_stop):self.a.scan(self.exports,0)
        self.assertEqual(len(self.a.catalog()),1)
        self.a.scan(self.exports,0);self.assertEqual(len(self.a.catalog()),2)
    def test_unchanged_nonchat_files_are_checkpointed(self):
        self.write('document.md','# Plain document\nThis is not a chat.')
        with patch.object(self.a,'read_items',wraps=self.a.read_items) as read:
            self.a.scan(self.exports,0);self.assertEqual(read.call_count,1)
            self.a.scan(self.exports,0);self.assertEqual(read.call_count,1);self.assertEqual(self.a.status['cached'],1)

class ForegroundTests(unittest.TestCase):
    setUp=ArchiveTests.setUp
    tearDown=ArchiveTests.tearDown
    write=ArchiveTests.write
    def test_manifest_catalog_available_before_message_index(self):
        f=self.write('json/chat.json',fixture('manifest-priority',n=110));manifest=self.write('conversation-index.json',{'entries':[]})
        self.a.register_manifest({'id':'manifest-priority','title':'Priority title','json':'json/chat.json'},manifest,self.exports)
        c=self.a.catalog()[0];self.assertFalse(c['loaded']);self.assertEqual(self.a.coverage()['available'],1);self.assertEqual(self.a.coverage()['indexed'],0)
        with self.a.foreground_read():page=self.a.page('manifest-priority')
        self.assertEqual(len(page['messages']),100);self.assertEqual(page['messages'][-1]['seq'],109)
        self.assertEqual(self.a.search('Priority title')['results'][0]['cid'],'manifest-priority')
        self.assertEqual(self.a.source_data('manifest-priority')[1],f)
    def test_manifest_missing_source_is_counted_separately(self):
        manifest=self.write('conversation-index.json',{'entries':[]})
        self.a.register_manifest({'id':'missing-chat','title':'Missing source','json':'json/missing.json'},manifest,self.exports)
        self.assertEqual(self.a.catalog(),[]);self.assertEqual(self.a.coverage()['expected'],1);self.assertEqual(self.a.coverage()['missing'],1)
    def test_generic_folder_names_are_scanned(self):
        for name in ('web','models','tests','runtime'):
            self.write(name+'/chat.json',fixture('export-'+name,n=2))
        self.a.scan(self.exports,0);self.assertEqual(len(self.a.catalog()),4)
    def test_manifest_organization_survives_lazy_catalog_and_indexing(self):
        self.write('json/chat.json',fixture('manifest-organized',n=2));manifest=self.write('conversation-index.json',{'entries':[]})
        entry={'id':'manifest-organized','title':'Priority title','json':'json/chat.json'}
        self.a.register_manifest(entry,manifest,self.exports);self.a.organize(entry['id'],{'category':'Study','pinned':1})
        self.assertEqual(self.a.catalog()[0]['category'],'Study');self.a.scan(self.exports,0);self.assertEqual(self.a.catalog()[0]['category'],'Study')
    def test_fts_row_mapping_migrates_existing_cache_without_stale_results(self):
        f=self.write('chat.json',fixture('migrate-fts',n=2));self.a.scan(self.exports,0)
        with self.a.connect() as db:
            db.execute("DELETE FROM settings WHERE key='ftsRowMapV1'");db.execute('DELETE FROM chunk_rows');db.execute('DELETE FROM title_rows')
        data=fixture('migrate-fts',n=2)
        for n in data['mapping'].values():
            if n.get('message'):n['message']['content']['parts']=['New unique replacement']
        f.write_text(json.dumps(data));self.a.scan(self.exports,0)
        self.assertTrue(self.a.search('unique replacement')['results']);self.assertFalse(self.a.search('electricity')['results'])
        with self.a.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM chunks').fetchone()[0],db.execute('SELECT count(*) FROM chunk_rows').fetchone()[0])
    def test_markdown_title_and_page_before_full_index(self):
        f=self.write('chat.md','# Unindexed title\nConversation: https://chatgpt.com/c/unindexed-md\n\n## You\nQuestion\n\n## Assistant\nAnswer')
        self.a.enable_ui_cache();self.a.announce_source(f,self.exports);self.a.publish_sources(list(self.a.live_sources.values()))
        self.assertEqual(self.a.state()['chats'][0]['id'],'unindexed-md');self.assertFalse(self.a.state()['chats'][0]['loaded'])
        with patch.object(self.a,'page',side_effect=AssertionError('Reader must bypass the index')):
            with self.a.foreground_read():page=self.a.foreground_page('unindexed-md',None,None,'100',False,None)
            self.assertEqual([m['text'] for m in page['messages']],['Question','Answer'])
    def test_selected_reader_runs_without_a_new_process(self):
        f=self.write('chat.md','# Thread read\n## You\nQuestion\n## Assistant\nAnswer')
        from viewer import source_page
        threads=[]
        def record(*args,**kwargs):threads.append(threading.current_thread().name);return source_page(*args,**kwargs)
        with patch('viewer.source_page',side_effect=record):page=self.a.read_source_page('thread-read',str(f),None,None,'100',False,None)
        self.assertEqual(page['total'],2);self.assertTrue(threads[0].startswith('SelectedChatReader'))
    def test_scan_worker_does_not_reinitialize_database(self):
        with patch.object(Archive,'connect',side_effect=AssertionError('Worker initialization must not touch SQLite')):
            worker=Archive(self.base/'data',initialize=False);worker.close()
    def test_spawned_scan_process_and_priority_read(self):
        self.a.background_process=True
        for i in range(30):self.write(f'chat-{i}.json',fixture(f'spawned-chat-{i}',n=20))
        self.a.request_scan(self.exports,0);deadline=time.monotonic()+10
        while self.a.status['scanning'] and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(self.a.status['scanning']);self.assertEqual(len(self.a.catalog()),30);self.assertEqual(self.a.page('spawned-chat-29')['total'],20)
        self.assertFalse(self.a.status['errors'])

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.a=Archive(self.tmp.name);self.s=Server(('127.0.0.1',0),self.a);self.thread=threading.Thread(target=self.s.serve_forever,daemon=True);self.thread.start();self.c=http.client.HTTPConnection('127.0.0.1',self.s.server_port)
    def tearDown(self):self.c.close();self.s.shutdown();self.s.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,method,path,body=None,headers=None):self.c.request(method,path,body,headers or {});r=self.c.getresponse();data=r.read();return r,data
    def test_auth_and_session_bootstrap(self):
        r,_=self.request('GET','/api/state');self.assertEqual(r.status,403)
        r,_=self.request('GET','/?token='+self.s.token);self.assertEqual(r.status,302);cookie=r.getheader('Set-Cookie').split(';')[0]
        r,body=self.request('GET','/api/state',headers={'Cookie':cookie});self.assertEqual(r.status,200);self.assertIn('chats',json.loads(body))
    def test_vendor_cache_does_not_cache_private_api_or_app_code(self):
        headers={'Cookie':'viewer_token='+self.s.token}
        r,_=self.request('GET','/vendor/marked.js?v=test',headers=headers);self.assertEqual(r.getheader('Cache-Control'),'private, max-age=86400')
        for path in ('/app.js','/api/state'):
            r,_=self.request('GET',path,headers=headers);self.assertEqual(r.getheader('Cache-Control'),'no-store')
    def test_two_viewers_share_browser_without_replacing_session_cookies(self):
        other=Server(('127.0.0.1',0),self.a)
        thread=threading.Thread(target=other.serve_forever,daemon=True);thread.start()
        client=http.client.HTTPConnection('127.0.0.1',other.server_port)
        try:
            r,_=self.request('GET','/?token='+self.s.token);first=r.getheader('Set-Cookie').split(';')[0]
            client.request('GET','/?token='+other.token);r=client.getresponse();r.read();second=r.getheader('Set-Cookie').split(';')[0]
            self.assertNotEqual(first.split('=')[0],second.split('=')[0])
            cookies={'Cookie':first+'; '+second}
            r,_=self.request('GET','/api/health',headers=cookies);self.assertEqual(r.status,200)
            client.request('GET','/api/health',headers=cookies);r=client.getresponse();r.read();self.assertEqual(r.status,200)
        finally:client.close();other.shutdown();other.server_close();thread.join()

    def test_cross_origin_write_and_host_rebinding_rejected(self):
        cookie='viewer_token='+self.s.token;r,_=self.request('POST','/api/settings','{}',{'Cookie':cookie,'Origin':'https://example.com'});self.assertEqual(r.status,403)
        r,_=self.request('GET','/api/state',headers={'Cookie':cookie,'Host':'evil.example'});self.assertEqual(r.status,403)
    def test_script_mime_independent_of_windows_file_associations(self):
        cookie='viewer_token='+self.s.token
        with patch('viewer.mimetypes.guess_type',side_effect=RuntimeError('registry unavailable')):
            for path,expected in [('/app.js','text/javascript'),('/boot.js','text/javascript'),('/style.css','text/css')]:
                r,_=self.request('GET',path,headers={'Cookie':cookie});self.assertEqual(r.status,200);self.assertTrue(r.getheader('Content-Type').startswith(expected))
    def test_state_read_remains_responsive_during_index_write(self):
        with self.a.connect() as writer:
            writer.execute('BEGIN IMMEDIATE');writer.execute("INSERT INTO settings VALUES('unfinished','true')")
            start=time.monotonic();r,body=self.request('GET','/api/state',headers={'Cookie':'viewer_token='+self.s.token})
            self.assertEqual(r.status,200);self.assertLess(time.monotonic()-start,1);self.assertNotIn('unfinished',json.loads(body)['settings'])
    def test_state_does_not_resend_unchanged_sidebar(self):
        headers={'Cookie':'viewer_token='+self.s.token};r,data=self.request('GET','/api/state',headers=headers);first=json.loads(data)
        r,data=self.request('GET','/api/state?since='+str(first['revision']),headers=headers);self.assertIsNone(json.loads(data)['chats'])
        self.a.organize('example-chat',{'pinned':1});r,data=self.request('GET','/api/state?since='+str(first['revision']),headers=headers);self.assertIsInstance(json.loads(data)['chats'],list)
    def test_cached_state_does_not_touch_database(self):
        self.a.enable_ui_cache();deadline=time.monotonic()+3
        while self.a.ui_cache['loading'] and time.monotonic()<deadline:time.sleep(.01)
        with patch.object(self.a,'catalog',side_effect=AssertionError('Catalog must not be read in HTTP state')),patch.object(self.a,'coverage',side_effect=AssertionError('Coverage must not be read in HTTP state')),patch.object(self.a,'settings',side_effect=AssertionError('Settings must not be read in HTTP state')):
            started=time.monotonic();r,data=self.request('GET','/api/state',headers={'Cookie':'viewer_token='+self.s.token});self.assertEqual(r.status,200);self.assertLess(time.monotonic()-started,.5);self.assertIsInstance(json.loads(data)['chats'],list)
            r,data=self.request('GET','/api/health',headers={'Cookie':'viewer_token='+self.s.token});self.assertEqual(r.status,200);self.assertEqual(json.loads(data)['version'],VERSION)
    def make_large_cache(self):
        self.a.enable_ui_cache();deadline=time.monotonic()+3
        while self.a.ui_cache['loading'] and time.monotonic()<deadline:time.sleep(.01)
        rows=[dict(id=f'chat-{i}',title='Unicode archive 測試 '+str(i),path='C:/exports/chat-'+str(i)+'.md',folder='exports',kind='chat',created=i,updated=i,url='',project='',loaded=True,count=100) for i in range(702)]
        self.a.publish_sources(rows)
        return rows
    def test_startup_only_five_titles_and_selected_chat_is_first(self):
        rows=self.make_large_cache();self.a.save_settings({'lastChat':'chat-701'})
        headers={'Cookie':'viewer_token='+self.s.token}
        r,data=self.request('GET','/api/state',headers=headers);state=json.loads(data)
        self.assertEqual(len(state['chats']),5);self.assertEqual(state['chats'][0]['id'],'chat-701')
        self.assertLess(len(data),8192);self.assertEqual(state['catalog']['total'],702)
        collected=state['chats'];offset=state['catalog']['nextOffset']
        while offset is not None:
            r,data=self.request('GET','/api/catalog?offset='+str(offset)+'&priority=chat-701',headers=headers);page=json.loads(data)
            self.assertLessEqual(len(page['chats']),25);self.assertLess(len(data),20*1024)
            collected.extend(page['chats']);offset=page['nextOffset']
        self.assertEqual(len(collected),702);self.assertEqual({c['id'] for c in collected},{c['id'] for c in rows})
    def test_catalog_batches_continue_during_discovery(self):
        rows=self.make_large_cache();first=self.a.state(limit=5,priority='not-yet-found')
        self.assertEqual(first['catalog']['priority'],'')
        new=dict(rows[0],id='not-yet-found');self.a.publish_sources([new])
        collected=first['chats'];offset=first['catalog']['nextOffset']
        while offset is not None:
            page=self.a.catalog_batch(offset,priority=first['catalog']['priority']);collected.extend(page['chats']);offset=page['nextOffset']
        self.assertEqual(len({c['id'] for c in collected}),703)
    def test_poll_omits_large_position_settings_and_catalog_uses_no_database(self):
        self.make_large_cache();self.a.save_settings({'positions':{f'chat-{i}':i for i in range(702)},'scan_up':2})
        state=self.a.state();headers={'Cookie':'viewer_token='+self.s.token}
        with patch.object(self.a,'catalog',side_effect=AssertionError('No DB catalog read')):
            r,data=self.request('GET','/api/state?since='+str(state['revision']),headers=headers);poll=json.loads(data)
            self.assertIsNone(poll['chats']);self.assertNotIn('positions',poll['settings']);self.assertEqual(poll['settings']['scan_up'],2)
            r,data=self.request('GET','/api/catalog?offset=5',headers=headers);self.assertEqual(len(json.loads(data)['chats']),25)
    def test_compressed_utf8_response_length_and_transfer_record(self):
        self.make_large_cache();headers={'Cookie':'viewer_token='+self.s.token,'Accept-Encoding':'gzip, deflate, br'}
        r,wire=self.request('GET','/api/catalog?offset=5',headers=headers)
        self.assertEqual(r.getheader('Content-Encoding'),'gzip');self.assertEqual(int(r.getheader('Content-Length')),len(wire))
        decoded=gzip.decompress(wire);self.assertGreater(len(decoded),len(wire)*2);self.assertIn('測試',decoded.decode())
        r,data=self.request('GET','/api/health',headers={'Cookie':'viewer_token='+self.s.token});record=json.loads(data)['transfers']['recent'][-1]
        self.assertEqual(record['endpoint'],'/api/catalog');self.assertEqual(record['bytes'],len(wire));self.assertEqual(record['written'],len(wire))
        self.assertNotIn('chat-5',json.dumps(record))
    def test_static_path_traversal_rejected(self):
        r,_=self.request('GET','/../viewer.py',headers={'Cookie':'viewer_token='+self.s.token});self.assertEqual(r.status,404)

if __name__=='__main__':unittest.main()
