import json, tempfile, unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from viewer import Archive

class FastTitles(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
        self.archive=Archive(self.base/'data', background_process=False)
        for cid,title in [('exact','Café expedition'),('prefix','Café expedition notes'),('alias','Original report'),('hidden','Café expedition')]:
            path=self.base/(cid+'.json');path.write_text(json.dumps(dict(id=cid,title=title,messages=[dict(role='user',content='Large message body unrelated to the title')])) )
            self.archive.store(next(self.archive.read_items(path)),path,'fixture',self.base,{})
        self.archive.organize('alias',dict(alias='Expedition checklist'))
        self.archive.organize('hidden',dict(trashed=1))
    def tearDown(self):self.archive.close();self.tmp.cleanup()
    def test_title_only_never_runs_message_fts(self):
        connection=self.archive.connect
        @contextmanager
        def guarded():
            with connection() as db:
                db.set_authorizer(lambda action,arg1,arg2,db_name,trigger: 1 if arg1 and (arg1=='messages' or str(arg1).startswith('chunks')) else 0)
                yield db
        with patch.object(self.archive,'connect',guarded):
            result=self.archive.search('cafe expedition','title')
        self.assertEqual(result['results'][0]['cid'],'exact')
        self.assertTrue(all(r['seq']==-1 for r in result['results']))
        self.assertNotIn('hidden',[r['cid'] for r in result['results']])
    def test_original_alias_typo_and_scopes(self):
        self.assertEqual(self.archive.search('original report','title')['results'][0]['cid'],'alias')
        self.assertEqual(self.archive.search('expediton','title')['results'][0]['match'],'Similar title')
        self.assertEqual(self.archive.search('expedition','title',cids={'alias'})['results'][0]['cid'],'alias')
        self.assertEqual(self.archive.search('anything','title',cids=set())['results'],[])
        self.archive.organize('alias',dict(alias='Renamed again'))
        self.assertEqual(self.archive.search('renamed again','title')['results'][0]['cid'],'alias')
    def test_empty_and_removed_results(self):
        self.assertEqual(self.archive.search('','title')['results'],[])
        self.assertEqual(self.archive.search('not a matching title','title')['results'],[])
