import json,tempfile,threading,unittest,urllib.parse,zipfile
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from archive_backup import BackupManager,digest
from discovery import scan_boundary
from viewer import Archive

class Links(HTMLParser):
    def __init__(self):super().__init__();self.paths=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.paths.extend(urllib.parse.unquote(v) for k,v in attrs if k=='href')

class LinkedBackup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'exports';self.root.mkdir();self.a=Archive(self.base/'.viewer-data',background_process=False);self.m=BackupManager(self.a,Path(__file__).parents[1]);self.a.save_settings({'scan_start':str(self.root),'scan_up':0})
    def tearDown(self):self.m.close();self.a.close();self.temp.cleanup()
    def export(self,root,cid='12345678-1111-2222-3333-123456789abc'):
        for name in ('markdown','json','attachments'): (root/name).mkdir(parents=True,exist_ok=True)
        md='markdown/Chat_'+cid+'.md';js='json/Chat_'+cid+'.json';asset='attachments/Chat_'+cid+'/drawing.png';(root/asset).parent.mkdir(exist_ok=True)
        (root/md).write_text('# Chat\n## You\n![Saved](../'+asset+')',encoding='utf-8');(root/js).write_text(json.dumps({'id':cid,'title':'Chat','messages':[{'role':'user','content':'Question'}]}),encoding='utf-8');(root/asset).write_bytes(b'original attachment')
        (root/'conversation-index.json').write_text(json.dumps({'entries':[{'id':cid,'title':'Chat','markdown':md,'json':js,'create_time':100,'update_time':200,'project':{'name':'Project'}}]}),encoding='utf-8');return md,js,asset
    def test_loader_scope_and_changes_use_identical_traversal(self):
        self.export(self.root);sibling=self.base/'other-export';sibling.mkdir();self.export(sibling,'87654321-1111-2222-3333-123456789abc');(self.base/'.viewer-data/hidden.md').write_text('Never included')
        for up in (0,1):
            self.a.save_settings({'scan_up':up});start,boundary=scan_boundary(self.root,up);status={'errors':[]}
            expected=set(self.a.discover_paths(start,boundary,threading.Event()));config,root,files,*_=self.m.inventory()
            docs={root/p for p in files if '/attachments/' not in '/'+p}
            self.assertEqual(docs,expected);self.assertEqual(config['up'],up);self.assertEqual(root,boundary);self.assertNotIn('private/hidden.md',files)
        self.a.save_settings({'scan_start':str(sibling),'scan_up':0});self.m.save_config({'source_mode':'loader','source':str(self.base/'no-longer-exists'),'up':4});self.assertEqual(self.m.config()['source'],str(sibling));self.assertEqual(self.m.preview()['root'],str(sibling));self.assertEqual(self.m.preview()['counts']['markdown'],1)
    def test_original_documents_and_every_index_link_present(self):
        paths=self.export(self.root);self.m.run(upload=False)
        with zipfile.ZipFile(self.m.local_path('full')) as z:
            self.assertIsNone(z.testzip());index=json.loads(z.read('archive-index.json'));self.assertEqual(len(index['conversations']),1);record=index['conversations'][0];self.assertEqual(record['project'],'Project');self.assertEqual(record['attachments'],[paths[2]])
            parser=Links();parser.feed(z.read('OPEN-ARCHIVE.html').decode());self.assertTrue(parser.paths);self.assertTrue(all(p in z.namelist() for p in parser.paths))
            for p in [*paths,'conversation-index.json']:self.assertEqual(z.read('archive/'+p),(self.root/p).read_bytes())
        (self.root/paths[0]).write_text('# New progress',encoding='utf-8');self.m.run(upload=False)
        with zipfile.ZipFile(self.m.local_path('progress')) as z:
            self.assertEqual(set(json.loads(z.read('backup-manifest.json'))['files']),{*paths,'conversation-index.json'})
    def test_desktop_route_has_stable_names_skips_unchanged_no_api(self):
        self.export(self.root);sync=self.base/'chosen-synced-folder';sync.mkdir();self.m.save_config({'sync_folder':str(sync),'route':'desktop'})
        with patch.object(self.m.drive,'upload',side_effect=AssertionError('API must not be used')):
            self.m.run();before={p.name:(digest(p)[0],p.stat().st_mtime_ns) for p in sync.glob('*.zip')};self.m.run();after={p.name:(digest(p)[0],p.stat().st_mtime_ns) for p in sync.glob('*.zip')};self.assertEqual(before,after);self.assertEqual(set(before),{'Chat-Archive-Full.zip','Chat-Archive-Progress.zip'})
            with patch('archive_backup.idle_seconds',return_value=601):
                config=self.m.config();config['enabled']=True
                from archive_backup import write_json
                write_json(self.m.config_path,config);self.assertFalse(self.m.due())
    def test_local_destination_survives_restart_without_cloud(self):
        self.export(self.root);dest=self.base/'visible-backups';self.m.save_config({'local_folder':str(dest)});self.m.run(upload=False);again=BackupManager(self.a,Path(__file__).parents[1])
        try:self.assertEqual(again.local_path('full'),dest/'Chat-Archive-Full.zip');self.assertTrue(again.status()['files']['full']['exists']);self.assertFalse(again.status()['connection']['connected']);self.assertIn('last_local',again.state())
        finally:again.close()
    def test_cancelled_copy_preserves_previous_complete_file(self):
        self.export(self.root);self.m.run(upload=False);sync=self.base/'sync';sync.mkdir();target=sync/'Chat-Archive-Full.zip';target.write_bytes(b'previous completed backup');self.m.cancel.set()
        with self.assertRaises(InterruptedError):self.m.publish_desktop(self.m.local_path('full'),sync,self.m.state()['slots']['full'],self.m.state())
        self.assertEqual(target.read_bytes(),b'previous completed backup');self.assertEqual(list(sync.glob('*.partial')),[])
    def test_stalled_foreground_read_cannot_starve_backup_or_cancel(self):
        done=threading.Event();self.a.foreground.set();worker=threading.Thread(target=lambda:(self.m.check(),done.set()),daemon=True);worker.start()
        try:
            self.assertTrue(done.wait(1),'A foreground read held the backup indefinitely')
            with patch.object(self.m.cancel,'wait',side_effect=lambda _:(self.m.cancel.set(),True)[1]):
                with self.assertRaises(InterruptedError):self.m.check()
        finally:self.a.foreground.clear();worker.join(1)

if __name__=='__main__':unittest.main()
