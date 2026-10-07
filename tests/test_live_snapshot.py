import json,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import archive_backup
from archive_backup import BackupManager
from viewer import Archive
from backup_snapshot import Snapshot,SnapshotPending
from drive_backup import save_private

class LiveSnapshot(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'exports';self.root.mkdir();(self.root/'chat.md').write_text('# Chat\nHello')
        (self.root/'attachments').mkdir();self.library=self.root/'attachments/library-catalog.html';self.library.write_text('saved catalog')
        self.a=Archive(self.base/'data',background_process=False)
        self.detect=patch('archive_backup.drive_suggestion',return_value={'sync_folder':''});self.detect.start()
        self.m=BackupManager(self.a,Path(__file__).parents[1]);self.m.save_config({'source':str(self.root),'modes':'both'})
    def tearDown(self):
        self.m.close()
        if self.m.worker:self.m.worker.join(5)
        self.a.close();self.detect.stop();self.temp.cleanup()
    def test_exporter_rewrites_catalog_after_inventory(self):
        original=archive_backup.build_zip
        def changing(root,*args,**kw):
            self.library.write_text('exporter is still writing a newer catalog')
            return original(root,*args,**kw)
        with patch('archive_backup.build_zip',side_effect=changing):self.m.run(False)
        with zipfile.ZipFile(self.m.local_path('full')) as z:
            self.assertEqual(z.read('archive/attachments/library-catalog.html'),b'saved catalog')
            manifest=json.loads(z.read('backup-manifest.json'));self.assertEqual(manifest['files']['attachments/library-catalog.html']['size'],len(b'saved catalog'))
    def test_capture_retries_in_background_and_survives_restart(self):
        self.m.run(False);previous=self.m.local_path('full').read_bytes()
        (self.root/'chat.md').write_text('# Chat\nUpdated while exporting')
        captured_chat=(self.root/'chat.md').read_bytes()
        self.library.write_text('new catalog')
        original=self.m.update;writes=[]
        def changing(**values):
            if values.get('phase')=='Capturing backup snapshot' and values.get('current')=='attachments/library-catalog.html':
                writes.append(1);self.library.write_text('catalog revision '+str(len(writes)))
            original(**values)
        with patch.object(self.m,'update',side_effect=changing):
            self.m.start(False);self.m.worker.join(5)
        self.assertEqual(len(writes),2);self.assertTrue(self.m.queue.status()['active'])
        self.assertEqual(self.m.status()['progress']['phase'],'Waiting for exporter')
        self.assertEqual(self.m.local_path('full').read_bytes(),previous)
        capture=self.m.snapshot;chat=capture.tree/'chat.md';before=chat.stat().st_mtime_ns
        # Original chat changes again, but this pending capture retains its verified revision.
        (self.root/'chat.md').write_text('a later export belongs to the next backup')
        state=self.m.state();state['capture_pending']['retry_at']=0;save_private(self.m.state_path,state)
        other=BackupManager(self.a,Path(__file__).parents[1])
        try:
            other.tick();other.worker.join(5)
            self.assertFalse(other.queue.status()['active']);self.assertFalse(other.status()['capture_pending'])
            self.assertEqual(chat.stat().st_mtime_ns,before)
            with zipfile.ZipFile(other.local_path('full')) as z:
                self.assertEqual(z.read('archive/chat.md'),captured_chat)
                self.assertEqual(z.read('archive/attachments/library-catalog.html'),self.library.read_bytes())
                manifest=json.loads(z.read('backup-manifest.json'))
                for path,value in manifest['files'].items():
                    import hashlib
                    self.assertEqual(hashlib.sha256(z.read('archive/'+path)).hexdigest(),value['sha256'])
        finally:other.close()
    def test_repeated_requests_reuse_exactly_two_zip_slots(self):
        target=self.base/'sync';target.mkdir();self.m.save_config({'sync_folder':str(target)})
        self.m.run(True);local={p.name:p.stat().st_mtime_ns for p in self.m.folder.glob('*.zip')};remote={p.name:p.stat().st_mtime_ns for p in target.glob('*.zip')}
        with patch('archive_backup.build_zip',side_effect=AssertionError('Unchanged ZIP must not be rebuilt')):self.m.run(True)
        self.assertEqual(local,{p.name:p.stat().st_mtime_ns for p in self.m.folder.glob('*.zip')})
        self.assertEqual(remote,{p.name:p.stat().st_mtime_ns for p in target.glob('*.zip')})
        self.assertEqual(set(local),{'Chat-Archive-Full.zip','Chat-Archive-Progress.zip'})
        self.library.write_text('next revision');self.m.run(True)
        self.assertEqual(set(remote),{p.name for p in target.glob('*.zip')})
    def test_cancellation_keeps_verified_captures_and_cleans_partial(self):
        def cancel(**values):raise InterruptedError('test cancellation')
        snapshot=Snapshot(self.base/'capture',self.root,'intent',cancel,lambda:None)
        with self.assertRaises(InterruptedError):snapshot.capture_many([self.root/'chat.md'])
        self.assertFalse(list(snapshot.tree.rglob('*.capture-partial')))
        self.assertTrue(snapshot.index.is_file())
    def test_staged_markdown_links_survive_source_rewrite(self):
        asset=self.root/'elsewhere/note.txt';asset.parent.mkdir();asset.write_text('linked attachment')
        (self.root/'chat.md').write_text('[note](elsewhere/note.txt)')
        original=archive_backup.build_zip
        def changing(root,*args,**kw):
            (self.root/'chat.md').write_text('new document');asset.write_text('later attachment')
            return original(root,*args,**kw)
        with patch('archive_backup.build_zip',side_effect=changing):self.m.run(False)
        with zipfile.ZipFile(self.m.local_path('full')) as z:
            self.assertEqual(z.read('archive/chat.md'),b'[note](elsewhere/note.txt)')
            self.assertEqual(z.read('archive/elsewhere/note.txt'),b'linked attachment')
    def test_damaged_capture_is_invalidated_and_recaptured(self):
        original=archive_backup.build_zip;damaged=[]
        def corrupt(root,*args,**kw):
            if not damaged:
                path=Path(root)/'attachments/library-catalog.html';s=path.stat()
                path.write_bytes(b'x'*s.st_size);os.utime(path,ns=(s.st_atime_ns,s.st_mtime_ns));damaged.append(True)
            return original(root,*args,**kw)
        with patch('archive_backup.build_zip',side_effect=corrupt):
            self.m.start(False);self.m.worker.join(5)
        self.assertTrue(self.m.status()['capture_pending'])
        self.assertNotIn('attachments/library-catalog.html',self.m.snapshot.state['files'])
        state=self.m.state();state['capture_pending']['retry_at']=0;save_private(self.m.state_path,state)
        self.m.tick();self.m.worker.join(5)
        self.assertFalse(self.m.status()['capture_pending'])
        with zipfile.ZipFile(self.m.local_path('full')) as z:self.assertEqual(z.read('archive/attachments/library-catalog.html'),self.library.read_bytes())
    def test_missing_local_preference_reuses_known_slot_folder(self):
        self.m.save_config({'local_folder':str(self.base/'older-version/Backups')});self.m.run(False)
        before=self.m.folder
        # Simulate a version with shared backup history but no saved destination.
        config=json.loads(self.m.config_path.read_text());config.pop('local_folder');self.m.config_path.write_text(json.dumps(config))
        other=BackupManager(self.a,Path(__file__).parents[1])
        try:self.assertEqual(Path(other.config()['local_folder']),before)
        finally:other.close()

if __name__=='__main__':unittest.main()
