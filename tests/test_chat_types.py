import sys,json,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from viewer import Archive,parse_json,canonical_kind,surface_signal

class ChatTypeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.a=Archive(self.root/'data',background_process=False)
    def tearDown(self):self.a.close();self.temp.cleanup()
    def store(self,cid,**extra):
        d={'id':cid,'title':'Work with Codex on a normal chat','messages':[{'role':'assistant','text':'```python\nprint(1)\n```'}],**extra};p=self.root/(cid+'.json');p.write_text(json.dumps(d));item=parse_json(d,p);self.a.store(item,p,'fp',self.root,{});return item
    def test_exporter_labels_normalize_without_using_project_as_work(self):
        for label in ('normal-chat','project-chat','unknown',None):self.assertEqual(canonical_kind(label),'chat')
        self.assertEqual(canonical_kind('ChatGPT Work'),'work');self.assertEqual(canonical_kind('codex-chat'),'codex')
        self.assertEqual(self.store('project',chat_kind='project-chat',project='Work')['kind'],'chat')
    def test_positive_surface_and_case_are_preserved(self):
        self.assertEqual(self.store('work',metadata={'surface':'ChatGPT Work'})['kind'],'work')
        self.assertEqual(self.store('codex',chatKind='CODEX',default_model_slug='example-wm')['kind'],'codex')
    def test_model_marker_is_labelled_as_inference(self):
        row=self.store('wm',default_model_slug='gpt-5.6-sol-wm');self.assertEqual(row['kind'],'work');self.assertIn('Inferred',row['kind_evidence'])
        self.assertEqual(self.store('chat',default_model_slug='gpt-5.6-thinking')['kind'],'chat')
    def test_code_and_titles_do_not_turn_chat_into_codex(self):self.assertEqual(self.store('normal')['kind'],'chat')
    def test_manifest_types_are_consistent_before_and_after_indexing(self):
        p=self.root/'normal.json';p.write_text(json.dumps({'id':'normal','messages':[{'role':'assistant','text':'Hello'}]}));manifest=self.root/'conversation-index.json';manifest.write_text('{}')
        e={'id':'normal','json':'normal.json','chat_kind':'normal-chat'};self.a.register_manifest(e,manifest,self.root)
        self.assertEqual(self.a.catalog()[0]['kind'],'chat');self.assertEqual(self.a.live_sources['normal']['kind'],'chat')
        self.a.store(parse_json(json.loads(p.read_text()),p),p,'fp',self.root,e);self.assertEqual(self.a.catalog()[0]['kind'],'chat')
    def test_cached_receipts_repair_work_without_reparsing_sources(self):
        self.store('cached')
        with self.a.connect() as db:db.execute('UPDATE messages SET extras=? WHERE cid=?',(json.dumps({'receipt':{'served':'gpt-5.6-sol-wm'}}),'cached'))
        (self.root/'cached.json').unlink();self.a.organize('cached',{'category':'Kept','alias':'Custom title'})
        self.a.enable_ui_cache();deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            c=self.a.ui_cache['chats'].get('cached')
            if c and c['kind']=='work':break
            time.sleep(.01)
        self.assertEqual(c['kind'],'work');self.assertEqual(c['category'],'Kept');self.assertEqual(c['alias'],'Custom title')
    def test_old_cache_uses_bounded_source_header_without_reindex(self):
        self.store('old',default_model_slug='gpt-5.6-sol-wm')
        p=self.root/'old.json';saved=json.loads(p.read_text())
        p.write_text(json.dumps({'default_model_slug':saved.pop('default_model_slug'),**saved}))
        with self.a.connect() as db:db.execute("UPDATE chats SET kind='chat',kind_evidence='' WHERE id='old'")
        self.a.repair_cached_types();self.assertEqual(self.a.catalog()[0]['kind'],'work')
        self.assertEqual(self.a.page('old')['total'],1)

    def test_generic_manifest_does_not_overwrite_work_model_evidence(self):
        self.store('wm',default_model_slug='gpt-5.6-sol-wm');self.a.enrich('wm',{'chat_kind':'normal-chat'});self.assertEqual(self.a.catalog()[0]['kind'],'work')
