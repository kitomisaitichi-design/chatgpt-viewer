import http.client,json,tempfile,threading,unittest
from pathlib import Path
from viewer import Archive,Server
from library_files import FileCatalog
from thread_images import ThreadImages,raster_type,message_images
from test_viewer import fixture

PNG=b'\x89PNG\r\n\x1a\n'+b'test bytes'

class ThreadImageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.a=Archive(self.root/'data',background_process=False);self.a.save_settings({'scan_start':str(self.root)});self.files=FileCatalog(self.a);self.images=ThreadImages(self.a,self.files);self.data=fixture(n=242);self.cid=self.data['conversation_id'];self.path=self.root/'chat.json';self.data['mapping']['n241']['message']['content']['parts']=['Final answer']
 def tearDown(self):self.a.close();self.tmp.cleanup()
 def save(self):
  self.path.write_text(json.dumps(self.data),encoding='utf-8');self.a.store(next(self.a.read_items(self.path)),self.path,'test',self.root,{})
 def image(self,name='one.png',content=PNG):
  p=self.root/'attachments'/name;p.parent.mkdir(exist_ok=True);p.write_bytes(content);return p
 def test_whole_thread_order_dedup_and_source_read_coalescing(self):
  self.image();self.image('two.png');self.data['mapping']['n0']['message']['content']['parts']=['First ![one](attachments/one.png)'];self.data['mapping']['n240']['message']['content']['parts']=['Last ![two](attachments/two.png) ![again](attachments/one.png)'];self.save();r=self.images.public(self.cid)
  self.assertEqual([i['seq'] for i in r['images']],[0,240]);self.assertEqual(r['images'][0]['sequences'],[0,240]);self.assertTrue(all(i['available'] for i in r['images']));reads=self.a.source_reader.reads;self.images.public(self.cid);self.assertEqual(self.images.builds,1);self.assertEqual(self.a.source_reader.reads,reads)
 def test_native_pointer_resolves_library_id_and_unlocated_library_is_last(self):
  p=self.image();self.image('library.png');index=self.root/'attachments/library-index.json';index.write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':[dict(id='file-one',name='one.png',path='attachments/one.png',size=len(PNG),status='saved',conversation_ids=[self.cid]),dict(id='file-library',name='library.png',path='attachments/library.png',status='saved',conversation_ids=[self.cid])]}));self.data['mapping']['n4']['message']['content']['parts']=[dict(content_type='image_asset_pointer',asset_pointer='sediment://file-one'),'Photo'];self.save();r=self.images.public(self.cid)['images'];self.assertEqual(len(r),2);self.assertEqual(r[0]['seq'],4);self.assertIsNone(r[1]['seq']);self.assertEqual(self.images.file(self.cid,r[0]['id']),p)
 def test_source_revision_and_branch_change_invalidate(self):
  self.image();self.image('two.png');self.data['mapping']['n0']['message']['content']['parts']=['![one](attachments/one.png)'];self.save();old=self.images.public(self.cid);self.data['mapping']['n0']['message']['content']['parts']=['![two](attachments/two.png)'];self.save();new=self.images.public(self.cid);self.assertNotEqual(old['revision'],new['revision']);self.assertIn('two.png',new['images'][0]['references'][0]);self.assertEqual(self.images.public(self.cid,'root')['images'],[])
 def test_missing_library_copy_appears_without_chat_reindex(self):
  p=self.root/'attachments/library-index.json';p.parent.mkdir();p.write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':[dict(id='late',name='late.png',expected_path='attachments/late.png',status='manual',conversation_ids=[self.cid])]}));self.save();self.assertFalse(self.images.public(self.cid)['images'][0]['available']);self.image('late.png');self.assertTrue(self.images.public(self.cid)['images'][0]['available']);self.assertEqual(self.images.builds,1)
 def test_remote_and_traversal_references_never_serve(self):
  self.data['mapping']['n0']['message']['content']['parts']=['![remote](https://example.org/p.png) ![outside](../../outside.png)'];self.save()
  for i in self.images.public(self.cid)['images']:
   self.assertFalse(i['available'])
   with self.assertRaises((FileNotFoundError,ValueError)):self.images.file(self.cid,i['id'])
 def test_html_disguised_as_png_rejected(self):
  self.image(content=b'<script>alert(1)</script>');self.data['mapping']['n0']['message']['content']['parts']=['![bad](attachments/one.png)'];self.save();item=self.images.public(self.cid)['images'][0]
  with self.assertRaises(ValueError):self.images.file(self.cid,item['id'])
 def test_missing_relative_image_can_arrive_without_index_rebuild(self):
  self.data['mapping']['n0']['message']['content']['parts']=['![late](attachments/late.png)'];self.save();item=self.images.public(self.cid)['images'][0];self.assertFalse(item['available']);p=self.image('late.png');self.assertTrue(self.images.public(self.cid)['images'][0]['available']);self.assertEqual(self.images.file(self.cid,item['id']),p);self.assertEqual(self.images.builds,1)
 def test_code_examples_are_not_images_but_local_html_is(self):
  self.image();self.data['mapping']['n0']['message']['content']['parts']=['```md\n![example](attachments/one.png)\n```\n`![also an example](attachments/one.png)`'];self.data['mapping']['n2']['message']['content']['parts']=['<img src="attachments/one.png" alt="Photo">'];self.save();items=self.images.public(self.cid)['images'];self.assertEqual(len(items),1);self.assertEqual(items[0]['seq'],2)
 def test_image_in_list_after_empty_message_keeps_correct_prompt(self):
  self.image();self.data={'id':self.cid,'messages':[{'role':'assistant','content':''},{'role':'user','content':{'parts':[{'content_type':'image_asset_pointer','asset_pointer':'attachments/one.png'}]}}]};self.save();items=self.images.public(self.cid)['images'];self.assertEqual(items[0]['seq'],0);self.assertTrue(items[0]['available'])
 def test_catalog_revision_changes_on_library_manifest_update(self):
  self.save();old=self.images.public(self.cid);self.image();(self.root/'attachments/library-index.json').write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':[dict(id='new',name='one.png',path='attachments/one.png',conversation_ids=[self.cid])]}));new=self.images.public(self.cid);self.assertNotEqual(old['revision'],new['revision']);self.assertEqual(len(new['images']),1)
 def test_metadata_does_not_extract_citation_icons_or_non_images(self):
  self.assertEqual(message_images(dict(content=dict(parts=['text']),metadata=dict(content_references=[dict(favicon_path='icons/x.png')],attachments=[dict(id='pdf',name='file.pdf')]))),[])
 def test_http_gallery_session_and_validated_image_content(self):
  self.image();self.data['mapping']['n0']['message']['content']['parts']=['![one](attachments/one.png)'];self.save();server=Server(('127.0.0.1',0),self.a);t=threading.Thread(target=server.serve_forever,daemon=True);t.start();c=http.client.HTTPConnection('127.0.0.1',server.server_port)
  try:
   path='/api/thread-images?id='+self.cid;c.request('GET',path);r=c.getresponse();self.assertEqual(r.status,403);r.read();cookie={'Cookie':server.cookie_name+'='+server.token};c.request('GET',path,headers=cookie);r=c.getresponse();item=json.loads(r.read())['images'][0];c.request('GET','/api/thread-images/content?id='+self.cid+'&image='+item['id'],headers=cookie);r=c.getresponse();self.assertEqual(r.status,200);self.assertEqual(r.getheader('Content-Type'),'image/png');self.assertEqual(r.read(),PNG)
  finally:c.close();server.shutdown();server.server_close();t.join()
