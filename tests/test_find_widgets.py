import json,tempfile,unittest,sys,threading,http.client
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from viewer import Archive,parse_json,presented_message,block_presentation,Server
from find_text import literal_matches,conversation_matches
from saved_widgets import saved_widgets,application_frame

def widget(value):return '\ue200genui\ue202'+json.dumps(value)+'\ue201'

class FindWidgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.a=Archive(self.root/'data',background_process=False)
        self.html='<h1>Counter</h1><script>document.body.dataset.ready="yes";</script>'
        self.data={'id':'fixture','title':'Search fixture','messages':[{'role':'user','text':'Needle in the prompt. Needle again.'},{'role':'assistant','text':'**Needle** in a table\n\n'+widget({'app_block':{'language':'html','content':self.html}})},{'role':'tool','text':'Needle in tool details.'}]}
        self.path=self.root/'fixture.json';self.path.write_text(json.dumps(self.data),encoding='utf-8');self.a.store(parse_json(self.data,self.path),self.path,'fixture',self.root,{})
    def tearDown(self):self.a.close();self.tmp.cleanup()
    def test_ordered_repeated_prompt_matches_and_hidden_tools(self):
        hits=conversation_matches(self.a,'fixture','needle')['results'];self.assertEqual([(h['seq'],h['start']) for h in hits],[(0,0),(0,22),(1,2)])
        self.assertEqual(len(conversation_matches(self.a,'fixture','needle',details=True)['results']),4)
    def test_literal_whitespace_unicode_and_regex_characters(self):
        self.assertEqual(len(literal_matches('RÉSUMÉ\n café [x+y] résumé café','résumé café')),2)
        self.assertEqual(literal_matches('a (x+y) b','(x+y)')[0]['text'],'(x+y)')
        self.assertEqual(literal_matches('ababa','aba')[0]['start'],0)
        self.assertEqual(len(literal_matches('x '*2000,'x',15)),15)
    def test_unknown_presentation_repairs_existing_cache(self):
        m=presented_message({'role':'assistant','text':'import numpy as np\nx=np.array([1,2])','extras':{'presentation':{'kind':'code','language':'unknown','origin':'saved'}}})
        self.assertEqual(m['extras']['presentation']['language'],'python')
        self.assertEqual(block_presentation("bash -lc python - <<'PY'\nimport json\nPY",'assistant',{'content_type':'code','language':'unknown'})['language'],'bash')
    def test_archive_scope_filters_before_ranking_limits(self):
        for mode in ('exact','exact_typo','keyword','smart'):
            self.assertTrue(self.a.search('Needle',mode,cids={'fixture'})['results'])
            self.assertEqual(self.a.search('Needle',mode,cids={'different'})['results'],[])
            self.assertEqual(self.a.search('Needle',mode,cids=set())['results'],[])
        self.a.save_settings({'kindOverrides':{'fixture':'work'}});self.a.organize_many([{'id':'fixture','category':'Research','position':10}]);self.assertEqual(next(c for c in self.a.catalog() if c['id']=='fixture')['category'],'Research')
    def test_assistant_tool_calls_are_hidden_but_final_code_is_visible(self):
        data={'id':'tool','mapping':{'a':{'id':'a','parent':None,'message':{'author':{'role':'assistant'},'recipient':'python','content':{'content_type':'code','language':'unknown','text':'print(1)'}}},'b':{'id':'b','parent':'a','message':{'author':{'role':'assistant'},'recipient':'all','content':{'content_type':'code','language':'python','text':'print(2)'}}}},'current_node':'b'}
        rows=parse_json(data,self.path)['messages'];self.assertEqual([m['visible'] for m in rows],[0,1])
    def test_saved_widgets_keep_nested_json_and_skip_literal_examples(self):
        w={'app_block':{'language':'html','content':'<script>const value=`a`; const nested={a:{b:2}};</script>'}}
        self.assertEqual(saved_widgets(widget({'citation':{'refs':['x']}})+widget(w)),[w])
        self.assertEqual(saved_widgets('~~~json\n'+widget(w)+'\n~~~'),[])
    def test_application_frame_validates_widget_and_color_values(self):
        text=widget({'app_block':{'language':'html','content':self.html}})
        result=application_frame(text,0,'body{margin:0}',{'bg':'#fff','text':'red;}</style><script>bad</script>'}).decode()
        self.assertIn('--viz-bg:#fff',result);self.assertNotIn('bad</script>',result);self.assertIn(self.html,result)
        for index in (-1,1):
            with self.assertRaises(ValueError):application_frame(text,index,'',{})
    def test_authenticated_frame_is_network_disabled_and_opaque(self):
        server=Server(('127.0.0.1',0),self.a);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        try:
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('GET','/api/app-frame?id=fixture&seq=1&widget=0',headers={'Cookie':'viewer_token='+server.token});r=c.getresponse();body=r.read().decode();self.assertEqual(r.status,200)
            csp=r.getheader('Content-Security-Policy');self.assertIn('sandbox allow-scripts',csp);self.assertIn("connect-src 'none'",csp);self.assertNotIn('allow-same-origin',csp);self.assertIn(self.html,body);c.close()
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('GET','/api/find?id=fixture&q=Needle',headers={'Cookie':'viewer_token='+server.token});r=c.getresponse();self.assertEqual(r.status,200);self.assertEqual(len(json.loads(r.read())['results']),3);c.close()
        finally:server.shutdown();server.server_close();t.join()

if __name__=='__main__':unittest.main()
