import http.client,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from viewer import Archive,Server
from library_files import FileCatalog,safe_relative

class FileCatalogTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'backup';self.root.mkdir();self.a=Archive(self.base/'data',background_process=False);self.a.save_settings({'scan_start':str(self.root)});self.catalog=FileCatalog(self.a)
 def tearDown(self):self.a.close();self.tmp.cleanup()
 def index(self,rows):
  p=self.root/'attachments/library-index.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':rows}),encoding='utf-8')
 def row(self,**changes):return dict(id='file-one',name='one.bin',size=4,status='manual',path=None,expected_path='attachments/library/file-one/one.bin',conversation_ids=['chat-one'],**changes)
 def test_import_manual_download_updates_availability_without_reindexing_chat(self):
  self.index([self.row()]);r=self.catalog.list()['entries'][0];source=self.base/'download.bin';source.write_bytes(b'data');self.catalog.import_copy(r['key'],source);r=self.catalog.list()['entries'][0];self.assertTrue(r['available']);self.assertEqual(r['status'],'saved');self.assertEqual(self.catalog.file(r['key'])[0].read_bytes(),b'data')
 def test_wrong_size_and_overwrite_preserve_original(self):
  self.index([self.row()]);key=self.catalog.list()['entries'][0]['key'];source=self.base/'download';source.write_bytes(b'bad')
  with self.assertRaises(ValueError):self.catalog.import_copy(key,source)
  source.write_bytes(b'data');self.catalog.import_copy(key,source)
  with self.assertRaises(ValueError):self.catalog.import_copy(key,source)
 def test_manifest_update_and_removed_file_are_detected_without_archive_rescan(self):
  self.index([self.row()]);self.assertEqual(self.catalog.list()['counts']['total'],1);self.index([self.row(),dict(id='two',name='two',status='saved',path='attachments/two')]);self.assertEqual(self.catalog.list()['counts']['total'],2);self.assertEqual(self.catalog.list(status='attention')['total'],2);self.assertEqual(self.catalog.list(conversation='chat-one')['total'],1)
 def test_paths_outside_backup_never_resolve(self):
  for p in ['../secret','attachments/../../secret','C:/secret','attachments\\file','/attachments/file']:
   self.assertIsNone(safe_relative(p))
  self.index([dict(id='outside',name='outside',path='../secret',status='saved')]);r=self.catalog.list()['entries'][0];self.assertFalse(r['available'])
  with self.assertRaises(FileNotFoundError):self.catalog.file(r['key'])
 def test_duplicate_ids_keep_saved_attachment_and_combine_source_chats(self):
  target=self.root/'attachments/old.bin';target.parent.mkdir();target.write_bytes(b'data');(self.root/'conversation-index.json').write_text(json.dumps({'entries':[{'id':'chat-two','attachments':[dict(id='file-one',name='one.bin',size=4,status='saved',path='attachments/old.bin')]}]}));self.index([self.row()]);r=self.catalog.list()['entries'][0];self.assertTrue(r['available']);self.assertEqual(r['conversations'],['chat-one','chat-two'])
 def test_catalog_construction_does_not_resolve_every_attachment_on_disk(self):
  self.index([dict(id=str(i),name='photo.jpeg',expected_path='attachments/library/'+str(i)+'/photo.jpeg') for i in range(1000)]);original=Path.resolve;calls=[]
  def resolve(path,*args,**kwargs):calls.append(path);return original(path,*args,**kwargs)
  with patch.object(Path,'resolve',resolve):self.catalog.refresh()
  self.assertLess(len(calls),30,'Catalog metadata must not traverse the filesystem once per attachment')
 def test_changed_symlink_cannot_escape_catalog_root_at_delivery(self):
  self.index([dict(id='file-one',name='one.bin',path='attachments/one.bin',size=4,status='saved')]);target=self.root/'attachments/one.bin';target.write_bytes(b'data');key=self.catalog.list()['entries'][0]['key'];outside=self.base/'outside';outside.mkdir();(outside/'one.bin').write_bytes(b'data');target.unlink()
  try:target.symlink_to(outside/'one.bin')
  except OSError:self.skipTest('Creating symlinks is unavailable')
  with self.assertRaises(FileNotFoundError):self.catalog.file(key)
 def test_service_error_copy_is_rejected(self):
  data=json.dumps({'status':'error','error_type':'file_not_found'}).encode();r=self.row();r['size']=len(data);self.index([r]);source=self.base/'bad';source.write_bytes(data)
  with self.assertRaises(ValueError):self.catalog.import_copy(self.catalog.list()['entries'][0]['key'],source)
 def test_http_requires_session_and_html_always_downloads(self):
  self.index([dict(id='html',name='page.html',size=9,path='attachments/page.html',status='saved')]);(self.root/'attachments/page.html').write_bytes(b'<script/>');server=Server(('127.0.0.1',0),self.a);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();c=http.client.HTTPConnection('127.0.0.1',server.server_port)
  try:
   c.request('GET','/api/files');r=c.getresponse();self.assertEqual(r.status,403);r.read();cookie={'Cookie':server.cookie_name+'='+server.token};c.request('GET','/api/files',headers=cookie);r=c.getresponse();key=json.loads(r.read())['entries'][0]['key'];c.request('GET','/api/files/content?inline=1&key='+key,headers=cookie);r=c.getresponse();self.assertEqual(r.status,200);self.assertEqual(r.getheader('Content-Type'),'application/octet-stream');self.assertIn('attachment',r.getheader('Content-Disposition'));self.assertEqual(r.read(),b'<script/>')
   c.request('POST','/api/files/import',body='{}',headers={**cookie,'Origin':'https://example.com','Content-Type':'application/json'});r=c.getresponse();self.assertEqual(r.status,403);r.read()
  finally:c.close();server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
