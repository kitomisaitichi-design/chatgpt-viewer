import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from viewer import Archive,parse_json
from phrase_search import near_phrase,edit_distance

class PhraseSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.a=Archive(self.root/'data',background_process=False)
        for cid,title,text in [('exact','Original record','The original conversation parser handles tables and formatting.'),('typo','Another record','The original conversatoin parser handles tables and formatting.'),('wrong','Unrelated','Original and unrelated words: parser then conversation.'),('unicode','Résumé notes','Résumé café 東京 notes.'),('complete','Long word','Semantic conversation rendering works offline.')]:
            p=self.root/(cid+'.json');data={'id':cid,'title':title,'messages':[{'role':'assistant','text':text}]};p.write_text('{}')
            self.a.store(parse_json(data,p),p,'fp',self.root,{})
    def tearDown(self):self.a.close();self.tmp.cleanup()
    def hits(self,q,mode='exact_typo',cid=None):return self.a.search(q,mode,cid)['results']
    def test_literal_matches_rank_before_spelling_matches(self):
        hits=self.hits('original conversation parser');self.assertEqual(hits[0]['cid'],'exact');self.assertEqual(hits[0]['match'],'Exact phrase');self.assertIn('typo',[h['cid'] for h in hits]);self.assertNotIn('wrong',[h['cid'] for h in hits])
    def test_missing_substituted_and_transposed_characters(self):
        for q in ['original converstion parser','original conversatoin parser','original conversaxion parser','original convesation parser']:
            self.assertIn('exact',[h['cid'] for h in self.hits(q)],q)
    def test_final_word_completion(self):
        hits=self.hits('conversation render');self.assertIn('complete',[h['cid'] for h in hits]);self.assertEqual(next(h for h in hits if h['cid']=='complete')['match'],'Prefix completion')
    def test_strict_search_preserves_phrase_order(self):
        self.assertEqual([h['cid'] for h in self.hits('original conversation parser','exact')],['exact']);self.assertEqual(self.hits('parser original conversation','exact'),[])
        self.assertEqual(self.hits('original conversaxion parser','exact'),[])
    def test_scope_and_unicode(self):
        self.assertEqual(self.hits('conversation',cid='unicode'),[])
        self.assertIn('unicode',[h['cid'] for h in self.hits('résumé café','exact')])
        self.assertIn('exact',[h['cid'] for h in self.hits('EXACT','exact')])
    def test_punctuation_and_fts_syntax_are_not_executed(self):
        for q in ['" OR *','foo:bar','NEAR(conversation,parser)','"conversation"']:
            self.hits(q)
    def test_short_terms_and_unrelated_words_are_conservative(self):
        self.assertIsNone(near_phrase('sun','cat'));self.assertIsNone(near_phrase('the unrelated words','original conversation'))
        self.assertEqual(edit_distance('teh','the'),1)
    def test_existing_database_gets_vocabulary_without_reindex(self):
        self.a.close();self.a=Archive(self.root/'data',background_process=False)
        self.assertIn('exact',[h['cid'] for h in self.hits('original conversatoin parser')])
