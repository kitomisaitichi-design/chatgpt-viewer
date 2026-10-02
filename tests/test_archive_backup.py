import hashlib,http.client,json,os,tempfile,threading,time,unittest,urllib.parse,urllib.request,zipfile
from pathlib import Path
from unittest.mock import patch
from archive_backup import BackupManager,build_zip,digest,extract_zip,job_lock,local_links,plan_files
from drive_backup import Drive,read_private,save_private,uploaded_offset
from viewer import Archive,Server

class Backups(unittest.TestCase):
    def setUp(self):
        detector=patch('archive_backup.drive_suggestion',return_value={'sync_folder':''});detector.start();self.addCleanup(detector.stop)
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'exports';self.root.mkdir();self.data=self.base/'data';self.a=Archive(self.data,background_process=False);self.manager=BackupManager(self.a,Path(__file__).parents[1])
        (self.root/'attachments').mkdir();(self.root/'attachments/picture.png').write_bytes(b'image bytes')
        (self.root/'notes.md').write_text('# Notes\n![Picture](attachments/picture.png)\n[Missing](files/not-saved.pdf)',encoding='utf-8');(self.root/'chat.json').write_text(json.dumps({'id':'backup-chat','title':'Backup chat','update_time':200,'messages':[{'role':'user','content':'Hello'}]}),encoding='utf-8');self.manager.save_config({'source':str(self.root)})
    def tearDown(self):self.manager.close();self.a.close();self.temp.cleanup()
    def test_links_and_boundary(self):
        self.assertIn('attachments/picture.png',local_links('![x](attachments/picture.png)'));self.assertIn('../files/a b.pdf',local_links('[x](<../files/a%20b.pdf>)'))
        (self.root/'outside.md').write_text('[outside](../secret.pdf)');(self.base/'secret.pdf').write_bytes(b'private');(self.root/'.viewer-data').mkdir();(self.root/'.viewer-data/session.json').write_text('{"token":"secret"}')
        files,fingerprint,missing=plan_files(self.root)
        self.assertIn('attachments/picture.png',files);self.assertNotIn('secret.pdf',files);self.assertNotIn('.viewer-data/session.json',files);self.assertTrue(any(m['reason'].startswith('Outside') for m in missing));self.assertEqual(len(fingerprint),64)
    def test_deterministic_zip_and_relative_links(self):
        files,fingerprint,missing=plan_files(self.root);manifest=dict(mode='full',files=files,missing=missing,fingerprint=fingerprint)
        first=self.base/'one.zip';second=self.base/'two.zip';build_zip(self.root,first,files,manifest);build_zip(self.root,second,files,manifest);self.assertEqual(first.read_bytes(),second.read_bytes())
        output=self.base/'restore';extract_zip(first,output);self.assertEqual((output/'archive/attachments/picture.png').read_bytes(),b'image bytes');self.assertIn('attachments/picture.png',(output/'archive/notes.md').read_text());self.assertEqual((self.root/'notes.md').read_text(),(output/'archive/notes.md').read_text())
    def test_changed_during_packaging_keeps_old_backup(self):
        files,_,_=plan_files(self.root);target=self.base/'latest.zip';target.write_bytes(b'previous completed backup');(self.root/'notes.md').write_text('changed')
        with self.assertRaises(ValueError):build_zip(self.root,target,files,{'mode':'full'})
        self.assertEqual(target.read_bytes(),b'previous completed backup')
    def test_unsafe_archive_paths(self):
        for index,name in enumerate(('../outside.txt','/absolute.txt','C:/drive.txt','a\\..\\outside.txt','CON.txt','nested/LPT1','nested/file.')):
            z=self.base/f'bad-{index}.zip'
            with zipfile.ZipFile(z,'w') as archive:archive.writestr(name,b'unsafe')
            with self.assertRaises(ValueError):extract_zip(z,self.base/f'bad-output-{index}')
        self.assertFalse((self.base/'outside.txt').exists())
    def test_uploads_update_same_slots_and_skip_unchanged(self):
        manager=self.manager;uploads=[]
        class FakeDrive:
            def status(self):return {'connected':True}
            def upload(self,path,folder,slot,checkpoint,progress,cancel):
                sha,md5=digest(path);identity=slot.get('id') or str(len(uploads)+1);uploads.append((identity,Path(path).name));progress(Path(path).stat().st_size,Path(path).stat().st_size)
                return dict(id=identity,md5Checksum=md5,size=str(Path(path).stat().st_size),webViewLink='https://drive.google.com/test/'+identity)
        manager.drive=FakeDrive();manager.save_config({'route':'api','folder_id':'chosen-folder'});manager.run();self.assertEqual(len(uploads),2);initial=manager.state()['slots'];manager.run();self.assertEqual(len(uploads),2)
        (self.root/'notes.md').write_text('# Updated\n![Picture](attachments/picture.png)');manager.run();self.assertEqual([u[0] for u in uploads],['1','2','1','2'])
        with zipfile.ZipFile(manager.folder/'Chat-Archive-Progress.zip') as z:
            manifest=json.loads(z.read('backup-manifest.json'));self.assertEqual(set(manifest['files']),{'notes.md','attachments/picture.png'});self.assertIn('viewer-settings.json',z.namelist())
        self.assertEqual(manager.state()['slots']['full']['id'],initial['full']['id'])
    def test_local_backup_needs_no_google_and_does_not_advance_upload_baseline(self):
        self.manager.run(upload=False);state=self.manager.state();self.assertNotIn('last_success',state);self.assertNotIn('baseline',state);self.assertTrue((self.manager.folder/'Chat-Archive-Full.zip').is_file());self.assertTrue((self.manager.folder/'Chat-Archive-Progress.zip').is_file())
    def test_partial_job_lock(self):
        with job_lock(self.data/'backup.lock'):
            with self.assertRaises(ValueError):
                with job_lock(self.data/'backup.lock'):pass
    def test_markdown_backup_restores_identity_dates_and_positions(self):
        path=self.root/'notes.md';path.write_text('# Notes\n## You\nQuestion\n## Assistant\n![Picture](attachments/picture.png)',encoding='utf-8');original=next(self.a.read_items(path));original.update(id='original-markdown-id',created=100,updated=200,kind='work');s=path.stat();self.a.store(original,path,str(s.st_mtime_ns)+':'+str(s.st_size),self.root,{})
        self.a.save_settings({'positions':{'original-markdown-id':3},'lastChat':'original-markdown-id','pageSize':50})
        self.manager.run(upload=False)
        other=Archive(self.base/'restored-data',background_process=False);manager=BackupManager(other,Path(__file__).parents[1])
        try:
            manager.import_zip(self.manager.folder/'Chat-Archive-Full.zip',restore_settings=True);manager.worker.join(10);self.assertEqual(manager.status()['progress']['phase'],'Import complete')
            catalog={c['id']:c for c in other.catalog()};restored=catalog['original-markdown-id'];self.assertEqual(restored['created'],100);self.assertEqual(restored['updated'],200);self.assertEqual(restored['kind'],'work');self.assertEqual(Path(restored['path']).stat().st_mtime_ns,s.st_mtime_ns)
            self.assertEqual(other.settings()['positions'],{'original-markdown-id':3});self.assertEqual(other.asset('original-markdown-id','attachments/picture.png').read_bytes(),b'image bytes')
        finally:manager.close();other.close()
    def test_backup_manifest_rejects_corrupt_file(self):
        self.manager.run(upload=False);source=self.manager.folder/'Chat-Archive-Full.zip';bad=self.base/'corrupt.zip'
        with zipfile.ZipFile(source) as old,zipfile.ZipFile(bad,'w') as new:
            for item in old.infolist():new.writestr(item,b'altered notes' if item.filename=='archive/notes.md' else old.read(item))
        with self.assertRaisesRegex(ValueError,'backup hash'):extract_zip(bad,self.base/'bad-restore')
    def test_import_integrates_and_keeps_newer_source(self):
        original=next(self.a.read_items(self.root/'chat.json'));s=(self.root/'chat.json').stat();self.a.store(original,self.root/'chat.json',str(s.st_mtime_ns)+':'+str(s.st_size),self.root,{})
        older=dict(id='backup-chat',title='Old backup',update_time=100,messages=[{'role':'user','content':'Old'}]);new=dict(id='new-chat',title='New imported',update_time=300,messages=[{'role':'user','content':'![saved](../attachments/picture.png)'}]);source=self.base/'import.zip'
        with zipfile.ZipFile(source,'w') as z:z.writestr('archive/json/old.json',json.dumps(older));z.writestr('archive/json/new.json',json.dumps(new));z.writestr('archive/attachments/picture.png',b'imported image')
        self.manager.import_zip(source);self.manager.worker.join(10);catalog={c['id']:c for c in self.a.catalog()};self.assertEqual(catalog['backup-chat']['title'],'Backup chat');self.assertEqual(catalog['new-chat']['title'],'New imported');self.assertEqual(self.a.asset('new-chat','../attachments/picture.png').read_bytes(),b'imported image');self.assertEqual(self.manager.status()['progress']['phase'],'Import complete')
    def test_schedule_requires_connection_and_idle(self):
        with patch('archive_backup.drive_suggestion',return_value={'sync_folder':''}):
            with self.assertRaises(ValueError):self.manager.schedule(True)
        self.assertFalse(self.manager.due())
    def test_idle_daily_due_gate(self):
        class Connection:
            def status(self):return {'connected':True}
        self.manager.drive=Connection();config=self.manager.save_config({'route':'api','folder_id':'folder'});config['enabled']=True
        from archive_backup import write_json
        write_json(self.manager.config_path,config);save_private(self.manager.state_path,{'last_success':time.time()-90000})
        with patch('archive_backup.idle_seconds',return_value=601):self.assertTrue(self.manager.due())
        with patch('archive_backup.idle_seconds',return_value=10):self.assertFalse(self.manager.due())
        config['cadence']='weekly';write_json(self.manager.config_path,config)
        with patch('archive_backup.idle_seconds',return_value=601):self.assertFalse(self.manager.due())

class GoogleConnection(unittest.TestCase):
    def test_private_connection_roundtrip_and_public_status(self):
        with tempfile.TemporaryDirectory() as temp:
            drive=Drive(temp);value=dict(client_id='test.apps.googleusercontent.com',refresh_token='private-refresh',access_token='private-access');save_private(drive.path,value);self.assertEqual(read_private(drive.path),value);self.assertNotIn('refresh_token',drive.status());self.assertNotIn('access_token',drive.status())
            if os.name=='nt':self.assertNotIn(b'private-refresh',drive.path.read_bytes())
            drive.disconnect();self.assertFalse(drive.status()['connected']);self.assertEqual(read_private(drive.path)['client_id'],value['client_id'])
    def test_oauth_pkce_and_state_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            drive=Drive(temp);drive.configure({'installed':{'client_id':'test.apps.googleusercontent.com','client_secret':'secret'}})
            with patch('drive_backup.webbrowser.open') as browser,patch.object(drive,'_token',return_value={'refresh_token':'refresh','access_token':'access','expires_in':3600}) as token,patch.object(drive,'request',return_value={'user':{'emailAddress':'example@example.test'}}):
                drive.connect();q=urllib.parse.parse_qs(urllib.parse.urlsplit(browser.call_args[0][0]).query);self.assertEqual(q['code_challenge_method'],['S256']);self.assertIn('drive.file',q['scope'][0]);self.assertIn('drive.metadata.readonly',q['scope'][0]);callback=q['redirect_uri'][0]
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(callback+'?code=fake&state=bad')
                urllib.request.urlopen(callback+'?'+urllib.parse.urlencode({'state':q['state'][0],'code':'fake'})).read();self.assertTrue(drive.status()['connected']);self.assertEqual(token.call_args[0][0]['redirect_uri'],callback);self.assertEqual(len(token.call_args[0][0]['code_verifier'])>=43,True)
                for _ in range(20):
                    if drive.listener._BaseServer__is_shut_down.is_set():break
                    time.sleep(.03)
    def test_wrong_client_and_session_endpoint_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            drive=Drive(temp)
            with self.assertRaises(ValueError):drive.configure({'web':{'client_id':'x'}})
            with self.assertRaises(ValueError):drive.request('PUT','https://example.test/upload',b'secret')
    def test_resumable_upload_and_existing_id(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'archive.zip';path.write_bytes(b'a'*(4*1024*1024+3));drive=Drive(temp);calls=[];slot={'id':'existing-backup'};events=[]
            def request(method,url,body=None,headers=None,raw=False):
                calls.append((method,url,headers))
                if method=='PATCH':return {'status':200,'headers':{'location':'https://www.googleapis.com/upload/drive/v3/files?upload_id=test'},'body':{}}
                if len(body)==4*1024*1024:return {'status':308,'headers':{'range':'bytes=0-4194303'},'body':{}}
                self.assertEqual(body,b'aaa');return {'status':200,'headers':{},'body':{'id':'existing-backup','size':str(path.stat().st_size),'md5Checksum':digest(path)[1]}}
            with patch.object(drive,'request',side_effect=request):
                result=drive.upload(path,'folder',slot,lambda:events.append('checkpoint'),lambda done,total:events.append(done),threading.Event())
            self.assertEqual(result['id'],'existing-backup');self.assertIn('/files/existing-backup?',calls[0][1]);self.assertEqual(calls[0][0],'PATCH');self.assertEqual(calls[-1][2]['Content-Range'],'bytes 4194304-4194306/4194307');self.assertIn('checkpoint',events)
            self.assertEqual(uploaded_offset({}),0);self.assertEqual(uploaded_offset({'range':'bytes=0-10'}),11)

if __name__=='__main__':unittest.main()
