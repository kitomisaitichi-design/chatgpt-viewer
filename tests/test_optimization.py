import json, tempfile, threading, unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from viewer import Archive, parse_json, parse_md, surface_signal, source_surface_hint, bounded_message_page
from source_reader import SourceReader
from chat_types import source_header

class ClassificationRegressionTests(unittest.TestCase):
    def test_attachments_and_failed_downloads_are_not_discovered_as_chats(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=Archive(root/'cache',background_process=False)
            try:
                (root/'attachments').mkdir();(root/'attachment-errors').mkdir()
                (root/'chat.json').write_text('{"id":"chat","messages":[]}')
                (root/'attachments'/'chat-copy.json').write_text('{"id":"copy","messages":[]}')
                (root/'attachment-errors'/'download.json').write_text('<html>Failed download</html>')
                (root/'failed.html.error-response.json').write_text('<html>Error</html>')
                self.assertEqual([p.name for p in a.discover_paths(root,root,threading.Event())],['chat.json'])
            finally:a.close()
    def test_paid_work_families_without_wm_suffix(self):
        for model in ('gpt-6-luna','gpt-6-terra','gpt-6-sol','gpt-6.1-sol','gpt-6-astra','gpt-6.1-astra','gpt-5.6-terra'):
            with self.subTest(model=model):self.assertEqual(surface_signal({'default_model_slug':model})[0],'work')
        for model in ('gpt-5-6-thinking','gpt-5-6','gpt-5-1-instant','gpt-4o'):
            self.assertIsNone(surface_signal({'default_model_slug':model}))
    def test_free_luna_exception(self):
        for flags in ({'account_plan':'free'},{'metadata':{'plan_type':'free'}},{'is_free_account':True},{'account':{'plan':'free'}}):
            self.assertIsNone(surface_signal({'default_model_slug':'gpt-6-luna',**flags}))
            self.assertEqual(surface_signal({'default_model_slug':'gpt-6-terra',**flags})[0],'work')
    def test_work_turn_on_inactive_branch_and_changed_default(self):
        data={'id':'mixed','default_model_slug':'gpt-5-6-thinking','current_node':'chat','mapping':{
            'chat':{'id':'chat','message':{'author':{'role':'assistant'},'content':{'parts':['Hello']}}},
            'work':{'id':'work','message':{'author':{'role':'assistant'},'metadata':{'model_slug':'gpt-6-sol'},'content':{'parts':['Saved other reply']}}}}}
        self.assertEqual(parse_json(data,Path('mixed.json'))['kind'],'work')
    def test_free_account_inherited_by_turns(self):
        data={'id':'free','account_plan':'free','messages':[{'role':'assistant','text':'Reply','metadata':{'model_slug':'gpt-6-luna'}}]}
        self.assertEqual(parse_json(data,Path('free.json'))['kind'],'chat')
        data['messages'][0]['metadata']['model_slug']='gpt-6-astra'
        self.assertEqual(parse_json(data,Path('free.json'))['kind'],'work')
    def test_arbitrary_source_labels_and_collab_are_not_codex(self):
        self.assertIsNone(surface_signal({'source':'I work with Codex on documents','metadata':{'codex_collab_agent_tool_call':{'tool':'wait'}}}))
        self.assertEqual(surface_signal({'originator':'codex_cli_rs'})[0],'codex')
    def test_header_never_reads_message_text_as_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.json';p.write_text(json.dumps({'id':'header','messages':[{'role':'user','text':'"product": "codex"'}],'default_model_slug':'gpt-6-sol'}))
            self.assertIsNone(source_surface_hint(p))
            p.write_text(json.dumps({'id':'header','default_model_slug':'gpt-6-sol','messages':[]}))
            self.assertEqual(source_surface_hint(p)[0],'work')
    def test_manifest_discovers_work_before_indexing_and_no_md_downgrade(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=Archive(root/'cache',background_process=False)
            try:
                p=root/'chat.json';p.write_text(json.dumps({'id':'chat','default_model_slug':'gpt-6.1-sol','messages':[{'role':'assistant','text':'Hello'}]}))
                manifest=root/'conversation-index.json';manifest.write_text('{}')
                a.register_manifest({'id':'chat','json':'chat.json','chat_kind':'unknown'},manifest,root)
                self.assertEqual(a.catalog()[0]['kind'],'work')
                md=root/'chat.md';md.write_text('# Chat\nConversation: https://chatgpt.com/c/chat\n## Assistant\nHello')
                a.announce_source(md,root);self.assertEqual(a.live_sources['chat']['kind'],'work')
                a.store(parse_json(json.loads(p.read_text()),p),p,'fp',root,{'chat_kind':'unknown'})
                rev=a.revision;a.enrich('chat',{'chat_kind':'unknown','url':'https://chatgpt.com/c/chat'})
                self.assertEqual(a.revision,rev)
            finally:a.close()
    def test_free_luna_cache_stays_chat_after_migration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=Archive(root/'cache',background_process=False)
            try:
                p=root/'free.json';data={'id':'free','account_plan':'free','messages':[{'role':'assistant','text':'Hello','metadata':{'model_slug':'gpt-6-luna'}}]};p.write_text(json.dumps(data))
                a.store(parse_json(data,p),p,'fp',root,{});p.unlink();a.repair_cached_types()
                self.assertEqual(a.catalog()[0]['kind'],'chat')
            finally:a.close()

class CacheAndTransferTests(unittest.TestCase):
    def test_manifest_refresh_preserves_index_status_until_source_changes(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'cache',background_process=False)
            try:
                a.enable_ui_cache();a.cache_thread.join(3)
                old={'id':'known','path':'known.json','fingerprint':'123:456','loaded':True,'count':80,'kind':'work'}
                a.publish_sources([old])
                a.publish_sources([{**old,'fingerprint':'','loaded':False,'count':0}])
                current=a.ui_cache['chats']['known']
                self.assertTrue(current['loaded']);self.assertEqual(current['fingerprint'],'123:456');self.assertEqual(current['count'],80)
                a.publish_sources([{**old,'fingerprint':'789:999','loaded':False,'count':0}])
                self.assertFalse(a.ui_cache['chats']['known']['loaded'])
            finally:a.close()
    def test_pages_fragments_and_branches_share_one_source_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=Archive(root/'cache',background_process=False)
            try:
                p=root/'source.json';p.write_text(json.dumps({'id':'source','messages':[{'role':'assistant','text':'α😀\\\n'*40000}]}))
                a.register_manifest({'id':'source','json':'source.json'},root/'manifest.json',root)
                a.enable_ui_cache();a.cache_thread.join(3)
                first=a.read_source_page('source',p,None,None,5,False,None)
                a.read_source_page('source',p,None,0,5,True,None)
                m=first['messages'][0];partial=bounded_message_page(first)['messages'][0]
                joined=partial['text'];offset=partial['text_next']
                while offset<len(m['text']):
                    part=a.message_fragment('source',0,offset,budget=65536);joined+=part['text'];offset=part['next_offset']
                self.assertEqual(joined,m['text']);self.assertEqual(a.source_reader.reads,1)
            finally:a.close()
    def test_concurrent_read_coalescing_and_changed_source_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source.json';p.write_text(json.dumps({'id':'coalesce','messages':[{'role':'assistant','text':'Before'}]}))
            reader=SourceReader(parse_json,parse_md);barrier=threading.Barrier(6)
            def read():barrier.wait();return reader.rows('coalesce',p)[0]['text']
            with ThreadPoolExecutor(max_workers=6) as pool:self.assertEqual(list(pool.map(lambda _:read(),range(6))),['Before']*6)
            self.assertEqual(reader.reads,1)
            p.write_text(json.dumps({'id':'coalesce','messages':[{'role':'assistant','text':'After and longer'}]}))
            self.assertEqual(reader.rows('coalesce',p)[0]['text'],'After and longer');self.assertEqual(reader.reads,2)
    def test_cache_eviction(self):
        with tempfile.TemporaryDirectory() as d:
            reader=SourceReader(parse_json,parse_md,max_entries=2)
            paths=[]
            for i in range(3):
                p=Path(d)/f'{i}.json';p.write_text(json.dumps({'id':str(i),'messages':[]}));paths.append(p);reader.rows(str(i),p)
            self.assertEqual(len(reader.entries),2)
            reader.rows('0',paths[0]);self.assertEqual(reader.reads,4)
    def test_fragment_only_queries_requested_indexed_message(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=Archive(root/'cache',background_process=False)
            try:
                p=root/'source.json';p.write_text(json.dumps({'id':'single','messages':[{'role':'assistant','text':'a'*150000}]}))
                a.store(next(a.read_items(p)),p,'fp',root,{})
                with patch.object(a,'foreground_page',side_effect=AssertionError('Must not fetch neighbours')):
                    result=a.message_fragment('single',0,10)
                self.assertEqual(result['next_offset'],10+len(result['text']))
            finally:a.close()
    def test_source_metadata_cannot_expand_page_body(self):
        message={'seq':0,'text':'Hello','extras':{'sources':{f'turn0search{i}':[{'url':'https://example.org/'+('x'*20000),'title':'X'}] for i in range(90)}}}
        page=bounded_message_page({'messages':[message],'total':1,'older':0,'newer':0,'first':0},8192)
        self.assertLess(len(json.dumps(page).encode()),8192)
    def test_branch_data_is_shared_and_updates_invalidate_it(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'branch.json';data={'id':'b','current_node':'one','mapping':{'one':{'id':'one','message':{'author':{'role':'assistant'},'content':{'parts':['One']}}},'two':{'id':'two','message':{'author':{'role':'assistant'},'content':{'parts':['Two']}}}}};p.write_text(json.dumps(data))
            r=SourceReader(parse_json,parse_md);self.assertEqual(r.rows('b',p,'one')[0]['text'],'One');self.assertEqual(r.rows('b',p,'two')[0]['text'],'Two');self.assertEqual(r.reads,1)
    def test_native_codex_uses_session_id_and_hides_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'session.jsonl';rows=[{'type':'session_meta','payload':{'id':'native-session','originator':'codex_cli_rs'}},{'type':'response_item','payload':{'role':'assistant','channel':'analysis','content':[{'text':'Private analysis'}]}},{'type':'response_item','payload':{'role':'assistant','channel':'final','content':[{'text':'Done'}]}}];p.write_text('\n'.join(json.dumps(x) for x in rows));a=Archive(root/'cache',background_process=False)
            try:
                item=next(a.read_items(p));self.assertEqual(item['id'],'native-session');self.assertEqual(item['kind'],'codex');self.assertFalse(item['messages'][0]['visible']);self.assertTrue(item['messages'][1]['visible'])
                self.assertEqual(a.source_reader.raw('native-session',p)['id'],'native-session')
                self.assertEqual(a.source_reader.rows('native-session',p)[1]['text'],'Done')
                self.assertEqual(a.source_reader.reads,1)
            finally:a.close()
