import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from archive_backup import BackupManager,digest,write_json
from drive_backup import save_private
from backup_queue import BackupQueue
from exporter_bridge import inspect_folder,read_metadata,META_LIMIT
from library_files import FileCatalog
from viewer import Archive

class ReliableBackups(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'exports';self.root.mkdir();(self.root/'chat.md').write_text('# Example\n## You\nHello')
        self.archive=Archive(self.base/'data',background_process=False)
        self.detector=patch('archive_backup.drive_suggestion',return_value={'sync_folder':''});self.detector.start()
        self.m=BackupManager(self.archive,Path(__file__).parents[1]);self.m.save_config({'source':str(self.root),'sync_folder':str(self.base/'unmounted'/'backups')})
    def tearDown(self):
        self.m.close()
        if self.m.worker:self.m.worker.join(5)
        self.archive.close();self.detector.stop();self.temp.cleanup()
    def test_offline_drive_keeps_both_completed_zips_for_retry(self):
        with self.assertRaises(ValueError):self.m.run(upload=True)
        self.assertTrue(self.m.local_path('full').is_file());self.assertTrue(self.m.local_path('progress').is_file())
        self.assertTrue(self.m.state()['delivery_pending']);self.assertTrue(self.m.state()['last_local'])
    def test_busy_requests_coalesce_instead_of_failing(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def run(upload):
            calls.append(upload);entered.set();release.wait(5)
        with patch.object(self.m,'run',side_effect=run):
            self.m.start(False);self.assertTrue(entered.wait(2))
            try:
                self.assertTrue(self.m.start(False)['queued']);self.assertTrue(self.m.start(True)['queued'])
                self.assertEqual(self.m.status()['queue']['pending'],2)
            finally:release.set();self.m.worker.join(5)
        self.assertEqual(calls,[False,False,True])
    def test_offline_retry_survives_restart_without_source_scan(self):
        with self.assertRaises(ValueError):self.m.run(True)
        hashes={mode:digest(self.m.local_path(mode))[0] for mode in ('full','progress')}
        self.root.rename(self.base/'source-offline');(self.base/'unmounted').mkdir()
        other=BackupManager(self.archive,Path(__file__).parents[1])
        try:
            with patch.object(other,'inventory',side_effect=AssertionError('Retry must use completed ZIPs')):other.resume_delivery()
            self.assertFalse(other.status()['delivery_pending'])
            for mode,sha in hashes.items():self.assertEqual(digest(self.base/'unmounted'/'backups'/self.m.local_path(mode).name)[0],sha)
        finally:other.close()
    def test_destination_change_never_redirects_automatic_retry(self):
        with self.assertRaises(ValueError):self.m.run(True)
        target=self.base/'different';target.mkdir();self.m.save_config({'sync_folder':str(target)})
        with self.assertRaisesRegex(ValueError,'destination changed'):self.m.resume_delivery()
        self.assertEqual(list(target.iterdir()),[])
    def test_cancel_pauses_delivery_until_explicit_retry(self):
        with self.assertRaises(ValueError):self.m.run(True)
        self.m.cancel_jobs();self.assertTrue(self.m.state()['delivery_pending']['paused'])
        (self.base/'unmounted').mkdir();self.m.retry_delivery();self.m.worker.join(5)
        self.assertFalse(self.m.status()['delivery_pending'])
    def test_tampered_cached_zip_is_rebuilt_before_copy(self):
        self.m.run(False);path=self.m.local_path('full');sha=digest(path)[0];path.write_bytes(b'corrupt')
        self.m.run(False);self.assertEqual(digest(path)[0],sha)
    def test_local_only_change_pauses_pending_mirror(self):
        with self.assertRaises(ValueError):self.m.run(True)
        (self.root/'chat.md').write_text('# Example\n## You\nNew private local text')
        self.m.run(False);self.assertTrue(self.m.state()['delivery_pending']['paused'])
        with self.assertRaisesRegex(ValueError,'ZIPs changed'):self.m.resume_delivery()
    def test_coalesced_intents_and_claim_survive_restart(self):
        self.m.queue.push('backup',False,True);self.m.queue.push('backup',False,False)
        queue=BackupQueue(self.m.queue.path,self.m.queue.lock)
        self.assertEqual(queue.status()['pending'],1);job=queue.claim(lambda j:True)
        self.assertFalse(job['upload']);self.assertFalse(job['scheduled'])
        self.assertEqual(BackupQueue(queue.path,queue.lock).claim(lambda j:True),job);queue.ack()
        self.assertEqual(queue.status(),{'pending':0,'active':False})
    def test_cancel_invalidates_active_intent_across_processes(self):
        self.m.queue.push('backup',False,True);job=self.m.queue.claim(lambda j:True)
        self.m.queue.clear();self.assertTrue(BackupQueue(self.m.queue.path,self.m.queue.lock).cancelled(job));self.assertFalse(self.m.queue.status()['active'])
    def test_local_only_intent_does_not_inherit_upload(self):
        self.m.queue.push('backup',True,True);self.m.queue.push('backup',False,False)
        uploads=[]
        for _ in range(2):uploads.append(self.m.queue.claim(lambda j:True)['upload']);self.m.queue.ack()
        self.assertEqual(uploads,[True,False])
    def test_crashed_claim_retries_delivery_without_repacking(self):
        self.m.queue.push('backup',True,False);self.m.current_job=self.m.queue.claim(lambda j:True)
        with self.assertRaises(ValueError):self.m.run(True)
        job=self.m.current_job;self.m.current_job=None;self.assertFalse(self.m.eligible(job))
        state=self.m.state();state['delivery_pending']['retry_at']=0;save_private(self.m.state_path,state)
        (self.base/'unmounted').mkdir();self.root.rename(self.base/'source-offline')
        with patch.object(self.m,'inventory',side_effect=AssertionError('Recovered claim must only deliver')):self.m.process_queue()
        self.assertFalse(self.m.status()['delivery_pending']);self.assertEqual(self.m.queue.status()['pending'],0)
    def test_waiting_idle_job_does_not_block_manual_request(self):
        self.m.queue.push('backup',False,True);self.m.queue.claim(lambda j:True)
        self.m.queue.push('mirror',True,False)
        job=self.m.queue.claim(lambda j:not j['scheduled']);self.assertEqual(job['kind'],'mirror')
    def test_retry_backoff_and_busy_tick_do_not_duplicate_work(self):
        with self.assertRaises(ValueError):self.m.run(True)
        with patch.object(self.m.queue,'push') as push:self.m.tick();push.assert_not_called()
        state=self.m.state();state['delivery_pending']['retry_at']=0;save_private(self.m.state_path,state)
        with patch.object(self.m,'kick'),patch.object(self.m.queue,'push') as push:self.m.tick();push.assert_called_once_with('retry',True,False)
    def test_exporter_updates_wait_for_quiet_period_and_idle(self):
        marker=self.root/'viewer-handoff.json';marker.write_text(json.dumps({'version':'2.4.10','entries':[]}))
        self.m.run(False);config=self.m.config();config.update(enabled=True,idle_required=False,ac_only=False);write_json(self.m.config_path,config)
        marker.write_text(json.dumps({'version':'2.4.10','entries':[],'updated':1}));state=self.m.state()
        self.assertFalse(self.m.exporter_changed(state));state=self.m.state();state['exporter_watch']['changed_at']-=121;save_private(self.m.state_path,state)
        self.assertTrue(self.m.exporter_changed(self.m.state()));self.m.save_config({'follow_exporter':False});self.assertFalse(self.m.exporter_changed(self.m.state()))
    def test_outer_folder_finds_nested_library_only_export(self):
        nested=self.root/'chatgpt-backup-scope';(nested/'attachments/content/hash').mkdir(parents=True)
        asset=nested/'attachments/content/hash/report.pdf';asset.write_bytes(b'report')
        row=dict(id='file-report',name='report.pdf',path='attachments/content/hash/report.pdf',size=6,status='saved')
        (nested/'viewer-handoff.json').write_text(json.dumps({'schema':'chatgpt-exporter-viewer/v1','version':'2.4.10','entries':[],'library':[row]}))
        (nested/'attachments/library-index.json').write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':[row]}))
        info=inspect_folder(self.root);self.assertEqual(info['exporter_version'],'2.4.10');self.assertIn(str(nested),info['exporter_roots']);self.assertTrue(info['has_library'])
        self.archive.scan(str(self.root),0);files=FileCatalog(self.archive).list()['entries']
        self.assertEqual(len(files),1);self.assertTrue(files[0]['available']);self.assertEqual(files[0]['name'],'report.pdf')
        self.m.run(False)
        import zipfile
        with zipfile.ZipFile(self.m.local_path('full')) as z:self.assertIn('archive/chatgpt-backup-scope/attachments/content/hash/report.pdf',z.namelist())
    def test_large_current_exporter_metadata_is_cached_and_invalidated(self):
        path=self.root/'viewer-handoff.json';data={'schema':'chatgpt-exporter-viewer/v1','version':'2.4.10','entries':[],'library':[],'unused_log':'x'*(33*1024**2)}
        path.write_text(json.dumps(data));first=read_metadata(path);self.assertEqual(first['version'],'2.4.10');self.assertNotIn('unused_log',first)
        with patch.object(Path,'read_text',side_effect=AssertionError('Unchanged metadata should reuse its parsed projection')):self.assertIs(read_metadata(path),first)
        path.write_text(json.dumps({'version':'2.4.10','entries':[{'id':'new-chat'}]}));self.assertEqual(read_metadata(path)['entries'][0]['id'],'new-chat')
    def test_folder_inspection_warm_cache_does_not_reparse_entries(self):
        path=self.root/'viewer-handoff.json';path.write_text(json.dumps({'version':'2.4.10','entries':[]}));inspect_folder(self.root)
        with patch('exporter_bridge.read_metadata',side_effect=AssertionError('Warm inspection should reuse its result')):self.assertEqual(inspect_folder(self.root)['exporter_version'],'2.4.10')
    def test_nested_duplicate_prefers_server_update_over_local_rewrite_time(self):
        import os
        outer=self.root/'json';nested=self.root/'nested/json';outer.mkdir();nested.mkdir(parents=True)
        for path,updated,text,mtime in [(outer/'chat.json',300,'Newest answer',100),(nested/'chat.json',200,'Old rewritten answer',200)]:
            path.write_text(json.dumps({'id':'duplicate-chat','title':'Duplicate','create_time':10,'update_time':updated,'messages':[{'role':'assistant','content':text}]}));os.utime(path,(mtime,mtime))
        self.archive.scan(str(self.root),0);self.assertEqual(self.archive.page('duplicate-chat')['messages'][0]['text'],'Newest answer')
        # Upgraded caches have no source timestamp; recover it from the bounded header.
        with self.archive.connect() as db:db.execute('UPDATE chats SET source_updated=0 WHERE id=?',('duplicate-chat',))
        self.archive.scan(str(self.root),0);self.assertEqual(self.archive.page('duplicate-chat')['messages'][0]['text'],'Newest answer')

if __name__=='__main__':unittest.main()
