import json, shutil, tempfile, threading, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from viewer import Archive
from preferences import Preferences, attach
from archive_backup import BackupManager
from backup_policy import retire_extras

class PreferenceControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.a=Archive(self.base/'v1',background_process=False)
    def tearDown(self):self.a.close();self.temp.cleanup()
    def chat(self,id='test-id'):
        source=self.base/(id+'.json');source.write_text(json.dumps({'id':id,'title':'Original title','messages':[{'role':'user','content':'needle'}]}))
        item=next(self.a.read_items(source));st=source.stat();self.a.store(item,source,f'{st.st_mtime_ns}:{st.st_size}',self.base,{})
        return item['id'],source
    def test_versions_share_names_trash_colors_order_and_backup_without_copying_sources(self):
        cid,path=self.chat();original=path.read_bytes();profile=self.base/'profile.json';attach(self.a,profile)
        self.a.save_settings({'theme':'black','positions':{cid:4},'scan_start':str(self.base)})
        self.a.organize(cid,{'alias':'New name','category':'My folder','pinned':1,'position':40,'trashed':1,'color':'#ef7895','sticky':1})
        self.a.profile.update(backup={'interval_hours':3,'cadence':'custom','idle_required':False,'auto_upload':False})
        b=Archive(self.base/'v2',background_process=False)
        try:
            attach(b,profile);self.assertEqual(b.settings()['theme'],'black')
            with b.connect() as db:row=dict(db.execute('SELECT * FROM organization WHERE cid=?',(cid,)).fetchone())
            self.assertEqual(row['alias'],'New name');self.assertEqual(row['trashed'],1);self.assertEqual(row['color'],'#ef7895');self.assertEqual(row['position'],40)
            self.assertEqual(json.loads((b.data_dir/'backup-config.json').read_text())['interval_hours'],3)
            b.organize(cid,{'trashed':0});self.assertEqual(Preferences(profile).read()['organization'][cid]['trashed'],0)
            self.assertEqual(path.read_bytes(),original);self.assertEqual(len(b.catalog()),0)
        finally:b.close()
    def test_parallel_profile_writes_keep_all_distinct_settings(self):
        path=self.base/'profile.json';p=Preferences(path)
        threads=[threading.Thread(target=lambda i=i:p.update(settings={f'key{i}':i})) for i in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(p.read()['settings'],{f'key{i}':i for i in range(8)})
    def test_reindexed_chat_stays_trashed_and_source_title_is_unchanged(self):
        cid,path=self.chat();self.a.organize(cid,{'alias':'Display','trashed':1,'color':'#65b5ed'})
        item=next(self.a.read_items(path));st=path.stat();self.a.store(item,path,f'{st.st_mtime_ns}:{st.st_size}',self.base,{})
        c=self.a.catalog()[0];self.assertEqual(c['title'],'Original title');self.assertEqual(c['alias'],'Display');self.assertEqual(c['trashed'],1)
    def test_one_edit_transfers_one_row_instead_of_whole_catalog(self):
        cid,_=self.chat();self.a.enable_ui_cache();self.a.cache_thread.join(5);revision=self.a.ui_cache['revision']
        self.a.organize(cid,{'color':'#65b5ed'})
        state=self.a.state(since=revision,limit=5);self.assertTrue(state['delta']);self.assertEqual([c['id'] for c in state['chats']],[cid]);self.assertNotIn('catalog',state)
    def test_invalid_color_cannot_reach_css(self):
        with self.assertRaises(ValueError):self.a.organize('test-id',{'color':'url(javascript:bad)'})
    def test_local_backup_interval_does_not_require_drive_or_idle(self):
        self.a.save_settings({'scan_start':str(self.base)})
        manager=BackupManager(self.a,Path(__file__).parents[1])
        try:
            manager.save_config({'interval_hours':3,'auto_upload':False,'idle_required':False,'ac_only':False})
            config=manager.config();config['enabled']=True
            with patch.object(manager,'config',return_value=config),patch.object(manager,'state',return_value={'last_local':10000}),patch('archive_backup.time.time',return_value=20799):self.assertFalse(manager.due())
            with patch.object(manager,'config',return_value=config),patch.object(manager,'state',return_value={'last_local':10000}),patch('archive_backup.time.time',return_value=20800):self.assertTrue(manager.due())
        finally:manager.close()
    def test_cleanup_preserves_unrelated_and_recovers_extra_viewer_archives(self):
        folder=self.base/'backups';folder.mkdir()
        for name in ('Chat-Archive-Full.zip','Chat-Archive-Full (1).zip','Chat-Archive-Progress.zip'):
            with zipfile.ZipFile(folder/name,'w') as z:z.writestr('backup-manifest.json',json.dumps({'schema':'offline-chat-viewer/backup-v1','name':name}))
        with zipfile.ZipFile(folder/'Chat-Archive-Unrelated.zip','w') as z:z.writestr('personal.txt','keep')
        moved=retire_extras(folder,['full']);self.assertEqual(len(moved),2);self.assertTrue((folder/'Chat-Archive-Full.zip').exists());self.assertTrue((folder/'Chat-Archive-Unrelated.zip').exists());self.assertTrue(all(Path(p).exists() for p in moved))
    def test_exact_duplicate_removed_only_after_byte_comparison(self):
        folder=self.base/'zips';folder.mkdir();full=folder/'Chat-Archive-Full.zip'
        with zipfile.ZipFile(full,'w') as z:z.writestr('backup-manifest.json',json.dumps({'schema':'offline-chat-viewer/backup-v1'}))
        copy=folder/'Chat-Archive-Full (copy).zip';shutil.copy2(full,copy)
        result=retire_extras(folder,['full']);self.assertEqual(result,['deduplicated:'+str(copy)]);self.assertFalse(copy.exists());self.assertTrue(full.exists())
    def test_schedule_xml_obeys_interval_idle_power_and_profile_path(self):
        self.a.save_settings({'scan_start':str(self.base)});attach(self.a,self.base/'profile.json');manager=BackupManager(self.a,Path(__file__).parents[1])
        try:
            manager.save_config({'interval_hours':6,'auto_upload':False,'idle_required':False,'ac_only':False})
            with patch('archive_backup.subprocess.run') as run:
                run.return_value.returncode=0;manager.schedule(True)
            text=(manager.data/'backup-task.xml').read_text(encoding='utf-16')
            self.assertIn('PT5M',text);self.assertIn('<RunOnlyIfIdle>false</RunOnlyIfIdle>',text);self.assertIn('<DisallowStartIfOnBatteries>false',text);self.assertIn('--profile',text)
            self.assertEqual(manager.config()['interval_hours'],6)
        finally:manager.close()
    def test_backup_history_and_lock_follow_profile_between_versions(self):
        profile=self.base/'profile.json';attach(self.a,profile);first=BackupManager(self.a,Path(__file__).parents[1])
        from drive_backup import save_private
        from archive_backup import job_lock
        save_private(first.state_path,{'last_success':123,'slots':{'full':{'sha256':'saved'}}})
        other=Archive(self.base/'v2',background_process=False);attach(other,profile)
        with job_lock(first.lock_path):second=BackupManager(other,Path(__file__).parents[1])
        try:
            self.assertEqual(first.lock_path,second.lock_path);self.assertEqual(second.state()['last_success'],123)
            with job_lock(first.lock_path):
                self.assertTrue(second.status()['running'])
        finally:first.close();second.close();other.close()

if __name__=='__main__':unittest.main()
