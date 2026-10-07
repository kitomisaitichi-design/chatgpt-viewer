import http.client,json,random,tempfile,threading,unittest,urllib.parse,zipfile
from pathlib import Path
from unittest.mock import patch
from exporter_bridge import entries,inspect_folder,attachment_records
from source_reader import IndexedRows,page_rows
from viewer import Archive,Server
from archive_backup import BackupManager
from library_files import FileCatalog

class ExporterInterop(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'export';self.root.mkdir();self.a=Archive(self.base/'data',background_process=False)
        (self.root/'json').mkdir();(self.root/'markdown').mkdir();(self.root/'attachments').mkdir();(self.root/'attachments/report.txt').write_text('Local report <script>alert(1)</script>',encoding='utf-8')
        self.raw={'id':'export-chat','title':'Exporter chat','create_time':10,'update_time':20,'is_starred':True,'messages':[{'role':'user','content':'Read report'},{'role':'assistant','content':'Saved answer'}]}
        (self.root/'json/chat.json').write_text(json.dumps(self.raw));(self.root/'markdown/chat.md').write_text('# Markdown twin\n## You\nRead report\n## Assistant\nSaved answer')
        self.entry={'id':'export-chat','title':'Exporter chat','chat_kind':'work','kind_evidence':'Saved Work product marker','create_time':10,'update_time':20,'project':{'name':'Research'},'json':'json/chat.json','markdown':'markdown/chat.md','attachments':[{'id':'file-report','name':'report.txt','path':'attachments/report.txt','status':'saved'},{'id':'missing','name':'lost.pdf','status':'unavailable'}]}
        self.index={'entries':[self.entry]};(self.root/'conversation-index.json').write_text(json.dumps(self.index))
        detector=patch('archive_backup.drive_suggestion',return_value={'sync_folder':''});detector.start();self.addCleanup(detector.stop)
    def tearDown(self):self.a.close();self.temp.cleanup()
    def import_archive(self,wrapper=''):
        z=self.base/'export.zip'
        with zipfile.ZipFile(z,'w') as archive:
            for p in self.root.rglob('*'):
                if p.is_file():archive.write(p,wrapper+p.relative_to(self.root).as_posix())
        manager=BackupManager(self.a,Path(__file__).parents[1]);self.addCleanup(manager.close);manager.import_zip(z);manager.worker.join(15)
        self.assertFalse(manager.worker.is_alive());self.assertEqual(manager.status()['progress']['phase'],'Import complete',manager.status());return manager
    def test_portable_state_merges_aliases_and_saved_index(self):
        result=entries({'job':{'entries':{'x':{'chatKind':'work','basename':'Title_x','updateTime':123}}},'index':{'entries':[{'id':'x','json':'json/actual.json','project':{'title':'Project'}}]}})[0]
        self.assertEqual(result['chat_kind'],'work');self.assertEqual(result['json'],'json/actual.json');self.assertEqual(result['project'],'Project');self.assertEqual(result['update_time'],123)
    def test_folder_inspector_finds_root_and_pending_files(self):
        info=inspect_folder(self.root/'json');self.assertEqual(info['root'],str(self.root));self.assertEqual(info['available'],1);self.assertEqual(info['missing'],0)
    def test_zip_import_keeps_richer_json_and_metadata_once(self):
        manager=self.import_archive();chat=self.a.catalog()[0]
        self.assertEqual(manager.state()['last_import']['indexed'],1);self.assertEqual(chat['project'],'Research');self.assertEqual(chat['kind'],'work');self.assertEqual(chat['created'],10);self.assertEqual(chat['updated'],20);self.assertEqual(chat['pinned'],1);self.assertEqual(Path(chat['path']).suffix,'.json')
        self.assertEqual(self.a.asset(chat['id'],'attachments/report.txt').read_text(),'Local report <script>alert(1)</script>');self.assertEqual(sum(f['available'] for f in self.a.saved_files(chat['id'])),1)
    def test_nested_zip_and_portable_state_only(self):
        (self.root/'conversation-index.json').unlink();(self.root/'portable-state.json').write_text(json.dumps({'job':{'entries':{}},'index':self.index}))
        self.import_archive('wrapped/backup/');self.assertEqual(self.a.catalog()[0]['project'],'Research');self.assertTrue(any(r['available'] for r in FileCatalog(self.a).list()['entries']))
    def test_import_does_not_reverse_manual_unpin_or_rename(self):
        self.import_archive();self.a.organize('export-chat',{'pinned':0,'alias':'My own title'});self.import_archive();chat=self.a.catalog()[0];self.assertEqual(chat['pinned'],0);self.assertEqual(chat['alias'],'My own title')
    def test_sparse_handoff_does_not_erase_project_during_scan(self):
        (self.root/'viewer-handoff.json').write_text(json.dumps({'entries':[{**self.entry,'project':''}]}))
        self.a.scan(self.root,0)
        self.assertEqual(self.a.catalog()[0]['project'],'Research')
    def test_cached_project_repair_keeps_content_and_manual_organization(self):
        self.import_archive();self.a.organize('export-chat',{'pinned':0,'category':'Personal','alias':'Mine'})
        with self.a.connect() as db:
            db.execute("UPDATE chats SET project='' WHERE id='export-chat'")
            before=[tuple(r) for r in db.execute('SELECT * FROM messages')]
            fingerprint=db.execute('SELECT fingerprint FROM chats').fetchone()[0]
        self.a.register_manifest({**self.entry,'project':''},self.root/'viewer-handoff.json',self.root)
        self.a.repair_cached_projects();chat=self.a.catalog()[0]
        self.assertEqual(chat['project'],'Research');self.assertEqual(chat['category'],'Personal');self.assertEqual(chat['alias'],'Mine');self.assertEqual(chat['pinned'],0)
        with self.a.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM messages')],before)
            self.assertEqual(db.execute('SELECT fingerprint FROM chats').fetchone()[0],fingerprint)
            db.execute("UPDATE chats SET project='' WHERE id='export-chat'")
        self.a.register_manifest({**self.entry,'project':'Conflicting'},self.root/'portable-state.json',self.root)
        self.a.repair_cached_projects();self.assertEqual(self.a.catalog()[0]['project'],'')
    def test_newer_existing_copy_is_kept(self):
        raw={**self.raw,'update_time':30};p=self.root/'json/chat.json';p.write_text(json.dumps(raw));self.a.store(next(self.a.read_items(p)),p,'current',self.root,{})
        p.write_text(json.dumps(self.raw));manager=self.import_archive();self.assertEqual(manager.state()['last_import']['indexed'],0);self.assertEqual(self.a.catalog()[0]['updated'],30)
    def test_attachment_paths_cannot_leave_export(self):
        outside=self.base/'secret.txt';outside.write_text('private');bad={'attachments':[{'path':'../secret.txt','name':'secret'}]};self.assertFalse(attachment_records(bad,self.root)[0]['available'])
    def test_partial_attachment_is_not_reported_as_complete(self):
        record=attachment_records({'attachments':[{'path':'attachments/report.txt','size':99999}]},self.root)[0];self.assertFalse(record['available']);self.assertEqual(record['status'],'incomplete')
    def test_stale_index_does_not_downgrade_json_timestamp(self):
        p=self.root/'json/chat.json';p.write_text(json.dumps({**self.raw,'update_time':30}));self.import_archive();self.assertEqual(self.a.catalog()[0]['updated'],30)
    def test_json_upgrades_an_equal_timestamp_markdown_copy(self):
        p=self.root/'markdown/chat.md';item=next(self.a.read_items(p));item.update(id='export-chat',created=10,updated=20);self.a.store(item,p,'old',self.root,{})
        self.import_archive();self.assertEqual(Path(self.a.catalog()[0]['path']).suffix,'.json')
    def test_attachment_json_is_not_indexed_as_a_conversation(self):
        (self.root/'files').mkdir();(self.root/'files/document.json').write_text(json.dumps({'id':'not-a-chat','messages':[{'role':'user','content':'A document containing chat-shaped JSON.'}]}));self.import_archive();self.assertEqual([c['id'] for c in self.a.catalog()],['export-chat'])
    def test_http_preview_is_bounded_and_html_downloads(self):
        self.a.register_manifest(self.entry,self.root/'conversation-index.json',self.root);(self.root/'attachments/report.txt').write_text('x'*40000)
        server=Server(('127.0.0.1',0),self.a);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();connection=http.client.HTTPConnection('127.0.0.1',server.server_port);cookie={'Cookie':server.cookie_name+'='+server.token}
        try:
            query=urllib.parse.urlencode({'id':'export-chat','path':'attachments/report.txt'});connection.request('GET','/api/file-preview?'+query,headers=cookie);response=connection.getresponse();data=json.loads(response.read());self.assertEqual(len(data['text']),32768);self.assertTrue(data['truncated'])
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Download should stream')):
                connection.request('GET','/api/asset?'+query,headers=cookie);response=connection.getresponse();self.assertEqual(response.status,200);self.assertIn('attachment',response.getheader('Content-Disposition'));self.assertEqual(len(response.read()),40000)
        finally:connection.close();server.shutdown();server.server_close();thread.join()

class IndexedPaging(unittest.TestCase):
    def test_pages_match_linear_reference_with_hidden_messages(self):
        rng=random.Random(5);rows=IndexedRows({'seq':i,'visible':bool(rng.randrange(2))} for i in range(2000))
        for details in (False,True):
            visible=list(rows) if details else [r for r in rows if r['visible']]
            for _ in range(100):
                seq=rng.randrange(2200);limit=rng.randrange(1,200);mode=rng.choice(('before','around','after'));actual=page_rows(rows,limit=limit,details=details,**{mode:seq})
                if mode=='before':selected=[r for r in visible if r['seq']<seq][-limit:]
                elif mode=='around':selected=[r for r in visible if r['seq']>=max(0,seq-8)][:limit]
                else:selected=[r for r in visible if r['seq']>seq][:limit]
                self.assertEqual(actual['messages'],selected);self.assertEqual(actual['total'],len(visible))
    def test_cached_pages_do_not_iterate_the_entire_source(self):
        class NoScan(IndexedRows):
            block=False
            def __iter__(self):
                if self.block:raise AssertionError('Repeated source scan')
                return super().__iter__()
        rows=NoScan({'seq':i,'visible':True} for i in range(50000));rows.block=True
        self.assertEqual(page_rows(rows,around=40000)['messages'][8]['seq'],40000);self.assertEqual(page_rows(rows,after=100)['messages'][0]['seq'],101)

if __name__=='__main__':unittest.main()
