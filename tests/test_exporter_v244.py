import csv,hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from archive_backup import BackupManager,digest,extract_zip
from exporter_bridge import inspect_folder
from folder_tools import drive_suggestion,quick_setup
from library_files import FileCatalog
from viewer import Archive

class Exporter244(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'export';self.root.mkdir()
        for name in ('json','markdown','attachments/shared'):(self.root/name).mkdir(parents=True)
        self.a=Archive(self.base/'data',background_process=False);self.a.save_settings({'scan_start':str(self.root),'scan_up':0})
        self.m=BackupManager(self.a,Path(__file__).parents[1]);self.m.save_config({'local_folder':str(self.base/'zips'),'sync_folder':''})
        self.cid='244-chat';self.asset='attachments/shared/content.pdf';self.image='attachments/shared/image.png'
        (self.root/self.asset).write_bytes(b'original file');(self.root/self.image).write_bytes(b'image bytes')
        self.write('json/chat.json',{'id':self.cid,'title':'Original title','messages':[{'role':'user','content':'Question'}]})
        (self.root/'markdown/chat.md').write_text('# Original title\n## You\nQuestion',encoding='utf-8')
        self.entry={'id':self.cid,'title':'Original title','json':'json/chat.json','markdown':'markdown/chat.md','attachments':[]}
        self.row={'id':'native-file','native_file_id':'native-file','name':'renamed.pdf','path':self.asset,'size':13,'sha256':digest(self.root/self.asset)[0],'status':'saved','source_refs':[{'kind':'chat','name':'original.pdf','conversationId':self.cid,'presence':'chat-unavailable'},{'kind':'library','name':'renamed.pdf','presence':'present'}]}
        self.write('viewer-handoff.json',{'schema':'chatgpt-exporter-viewer/v1','version':'2.4.4','entries':[self.entry],'library':[self.row]})
    def tearDown(self):self.m.close();self.a.close();self.tmp.cleanup()
    def write(self,path,value):(self.root/path).write_text(json.dumps(value),encoding='utf-8')
    def test_handoff_only_folder_detection_and_file_history(self):
        info=inspect_folder(self.root/'json');self.assertEqual(info['root'],str(self.root));self.assertEqual(info['exporter_version'],'2.4.4');self.assertEqual(info['available'],1)
        files=FileCatalog(self.a);row=files.list(search='original.pdf',source='chat')['entries'][0]
        self.assertEqual(row['conversations'],[self.cid]);self.assertTrue(row['available']);self.assertTrue(row['retained']);self.assertEqual(files.list(source='library')['total'],1)
    def test_shared_library_asset_travels_with_changed_conversation(self):
        self.m.run(upload=False);(self.root/'markdown/chat.md').write_text('# Updated\n## You\nNew question',encoding='utf-8');self.m.run(upload=False)
        with zipfile.ZipFile(self.m.local_path('progress')) as z:
            names=z.namelist();self.assertIn('archive/'+self.asset,names);self.assertIn('archive/json/chat.json',names)
            self.assertEqual(json.loads(z.read('archive-index.json'))['conversations'][0]['attachments'],[self.asset])
    def test_selective_types_keep_hashes_state_and_existing_links(self):
        self.m.save_config({'include_formats':['markdown','images']});self.m.run(upload=False)
        with zipfile.ZipFile(self.m.local_path('full')) as z:
            names=z.namelist();self.assertIn('archive/'+self.image,names);self.assertNotIn('archive/'+self.asset,names);self.assertNotIn('archive/json/chat.json',names);self.assertIn('archive/viewer-handoff.json',names)
            manifest=json.loads(z.read('backup-manifest.json'));self.assertEqual(manifest['include_formats'],['markdown','images'])
            rows=json.loads(z.read('save-state.json'))['files'];table=list(csv.DictReader(io.StringIO(z.read('save-state.csv').decode())))
            self.assertEqual(len(rows),len(table));self.assertEqual(len(rows),len(manifest['files']))
            for row in rows:self.assertEqual(row['sha256'],hashlib.sha256(z.read(row['path'])).hexdigest())
            from test_linked_backup import Links
            links=Links();links.feed(z.read('OPEN-ARCHIVE.html').decode());self.assertTrue(all(p in names for p in links.paths))
        extract_zip(self.m.local_path('full'),self.base/'unpacked')
    def test_unselected_large_assets_are_not_hashed(self):
        self.m.save_config({'include_formats':['json']})
        import archive_backup
        real=archive_backup.digest
        def guarded(path,check=lambda:None):
            self.assertNotIn(Path(path).suffix,('.pdf','.png'));return real(path,check)
        with patch('archive_backup.digest',side_effect=guarded):self.m.inventory(True,{})
    def test_attachment_only_backup_keeps_source_chat_cross_links(self):
        self.m.save_config({'include_formats':['files']});self.m.run(upload=False)
        with zipfile.ZipFile(self.m.local_path('full')) as z:
            record=json.loads(z.read('archive-index.json'))['conversations'][0];self.assertEqual(record['id'],self.cid);self.assertEqual(record['attachments'],[self.asset]);self.assertEqual(record['markdown'],[])
            group=json.loads(z.read('indexes/files.json'));row=next(r for r in group['files'] if r['original_path']==self.asset);self.assertEqual(row['conversation_ids'],[self.cid])
    def test_policy_changes_do_not_claim_excluded_files_were_deleted(self):
        self.m.run(upload=False);self.m.save_config({'include_formats':['markdown']});self.m.run(upload=False)
        with zipfile.ZipFile(self.m.local_path('progress')) as z:self.assertEqual(json.loads(z.read('backup-manifest.json'))['deleted'],[])
        (self.root/'markdown/chat.md').unlink()
        with self.assertRaisesRegex(ValueError,'No files match'):self.m.run(upload=False)
    def test_empty_type_selection_rejected_and_preferences_included(self):
        with self.assertRaises(ValueError):self.m.save_config({'include_formats':[]})
        self.a.save_settings({'sidebarWidth':420,'sidebarDates':False,'catalogFilters':{'read':'unread'},'readChats':{self.cid:{'updated':123}}});self.m.run(upload=False)
        with zipfile.ZipFile(self.m.local_path('full')) as z:
            prefs=json.loads(z.read('viewer-settings.json'))['settings'];self.assertEqual(prefs['sidebarWidth'],420);self.assertFalse(prefs['sidebarDates']);self.assertIn(self.cid,prefs['readChats'])
    def test_migration_uses_existing_verified_zips_with_missing_source(self):
        self.m.run(upload=False);before={m:digest(self.m.local_path(m))[0] for m in ('full','progress')};sync=self.base/'sync';sync.mkdir();self.m.save_config({'sync_folder':str(sync)})
        self.root.rename(self.base/'source-offline')
        with patch.object(self.m,'inventory',side_effect=AssertionError('Migration must not rescan')):
            self.m.migrate();self.m.worker.join(10)
        self.assertFalse(self.m.worker.is_alive());self.assertEqual(self.m.status()['progress']['phase'],'Completed ZIPs copied',self.m.status())
        for mode,sha in before.items():self.assertEqual(digest(sync/self.m.local_path(mode).name)[0],sha)
    def test_historical_versions_and_conflicting_hashes_stay_separate(self):
        self.write('conversation-index.json',{'entries':[dict(self.entry,attachments=[dict(self.row,id='native-file',file_id='native-file')])]})
        latest={**self.row,'path':'attachments/missing.pdf','sha256':'a'*64,'source_refs':[{'kind':'chat','name':'latest.pdf','presence':'present'}]}
        old={**self.row,'id':'native-file:saved:old','file_id':'native-file','historical':True,'source_refs':[{'kind':'chat','name':'old.pdf','conversationId':self.cid,'presence':'previous-version'}]}
        self.write('attachments/library-index.json',{'schema':'chatgpt-library-index/v1','entries':[latest,old]})
        files=FileCatalog(self.a);self.assertEqual(files.list()['total'],2);self.assertEqual(files.list(source='history')['total'],1);self.assertTrue(files.list(source='history')['entries'][0]['available'])
        current=next(r for r in files.list()['entries'] if not r['historical']);self.assertFalse(current['available'])
    def test_migration_rejects_tampered_zip_before_replacing_destination(self):
        self.m.run(upload=False);sync=self.base/'sync';sync.mkdir();self.m.save_config({'sync_folder':str(sync)})
        target=sync/self.m.local_path('full').name;target.write_bytes(b'previous complete backup');self.m.local_path('full').write_bytes(b'tampered')
        self.m.migrate();self.m.worker.join(10);self.assertEqual(target.read_bytes(),b'previous complete backup');self.assertIn('saved hash',self.m.status()['progress']['error'])
    def test_chat_only_retained_catalog_record_is_not_labeled_library(self):
        (self.root/'viewer-handoff.json').unlink();self.row['source_refs']=self.row['source_refs'][:1]
        self.write('attachments/library-index.json',{'schema':'chatgpt-library-index/v1','entries':[self.row]})
        files=FileCatalog(self.a);self.assertEqual(files.list(source='library')['total'],0);self.assertEqual(files.list(source='chat')['total'],1);self.assertEqual(files.list(source='retained')['total'],1)
    def test_detect_mirrored_drive_and_handoff_export(self):
        google=self.base/'GoogleDrive';(google/'My Drive').mkdir(parents=True);suggest=drive_suggestion([google]);self.assertEqual(suggest['root'],str(google/'My Drive'))
        result=quick_setup({},self.base/'app',downloads=self.base);self.assertIn(str(self.root),result['source_candidates']);self.assertFalse(Path(suggest['sync_folder']).exists())

if __name__=='__main__':unittest.main()
