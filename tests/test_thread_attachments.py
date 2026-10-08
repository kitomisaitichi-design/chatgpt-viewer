import http.client,json,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import test_thread_images as fixtures
from thread_attachments import ThreadAttachments,thread_markdown
from viewer import Server
import threading

class Attachments(unittest.TestCase):
 setUp=fixtures.ThreadImageTests.setUp
 tearDown=fixtures.ThreadImageTests.tearDown
 save=fixtures.ThreadImageTests.save
 def documents(self):
  self.save();self.docs=ThreadAttachments(self.a,self.files);folder=self.root/'attachments';folder.mkdir(exist_ok=True);return folder
 def index(self,items):
  (self.root/'attachments/library-index.json').write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':[dict(conversation_ids=[self.cid],**i) for i in items]}))
 def test_native_document_metadata_and_full_thread_order(self):
  folder=self.documents();(folder/'report.md').write_text('# Original');(folder/'book.xlsx').write_text('placeholder');self.index([dict(id='report-id',name='report.md',path='attachments/report.md'),dict(id='book-id',name='book.xlsx',path='attachments/book.xlsx')]);self.data['mapping']['n240']['message']['metadata']['attachments']=[dict(id='report-id',name='report.md')];self.save();items=self.docs.public(self.cid)['attachments'];self.assertEqual([i['kind'] for i in items],['markdown','sheet']);self.assertEqual(items[0]['seq'],240);self.assertIsNone(items[1]['seq']);self.assertTrue(items[0]['available'])
 def test_ambiguous_filename_is_not_assigned_to_prompt(self):
  folder=self.documents();(folder/'a').mkdir();(folder/'b').mkdir();(folder/'a/report.md').write_text('a');(folder/'b/report.md').write_text('b');self.index([dict(id='a-id',name='report.md',path='attachments/a/report.md'),dict(id='b-id',name='report.md',path='attachments/b/report.md')]);self.data['mapping']['n4']['message']['metadata']['attachments']=[dict(id='report.md',name='report.md')];self.save();items=self.docs.public(self.cid)['attachments'];self.assertFalse(any(i['seq']==4 and i['available'] for i in items));self.assertEqual(sum(i['available'] for i in items),2)
 def test_cached_delivery_missing_arrival_and_mutation(self):
  folder=self.documents();self.index([dict(id='late',name='late.txt',path='attachments/late.txt',size=4)]);item=self.docs.public(self.cid)['attachments'][0];self.assertFalse(item['available']);(folder/'late.txt').write_text('done');item=self.docs.public(self.cid)['attachments'][0];self.assertTrue(item['available']);old=item['modified']
  with patch.object(self.files,'refresh',side_effect=AssertionError('Catalog rebuilt during delivery')):self.assertEqual(self.docs.file(self.cid,item['id']).read_text(),'done')
  (folder/'late.txt').write_text('changed-size')
  with self.assertRaises(FileNotFoundError):self.docs.file(self.cid,item['id'])
 def test_branch_and_traversal_are_isolated(self):
  folder=self.documents();(folder/'report.md').write_text('body');self.data['mapping']['n240']['message']['content']['parts']=['[report](attachments/report.md) [bad](../../private.txt)'];self.save();items=self.docs.public(self.cid)['attachments'];self.assertTrue(any(i['available'] for i in items));self.assertFalse(self.docs.public(self.cid,'root')['attachments']);bad=next(i for i in items if not i['available'])
  with self.assertRaises((FileNotFoundError,ValueError)):self.docs.file(self.cid,bad['id'])
 def test_original_markdown_and_selected_branch_fallback(self):
  self.documents();md=self.root/'original.md';md.write_text('# Exact original\n\n'+'Long body\n'*10000);manifest=self.root/'conversation-index.json';entry=dict(id=self.cid,title='Fixture',json='chat.json',markdown='original.md');manifest.write_text(json.dumps({'entries':[entry]}));self.a.register_manifest(entry,manifest,self.root);text,mode=thread_markdown(self.a,self.cid);self.assertEqual(mode,'original');self.assertEqual(text,md.read_text());generated,mode=thread_markdown(self.a,self.cid,'root');self.assertEqual(mode,'generated');self.assertNotIn('Long body',generated)
 def test_office_zip_expansion_guard_and_original_access(self):
  folder=self.documents();p=folder/'bad.docx';p.write_bytes(b'not a ZIP');self.data['mapping']['n4']['message']['content']['parts']=['[Word](attachments/bad.docx)'];self.save();item=self.docs.public(self.cid)['attachments'][0]
  with self.assertRaises(zipfile.BadZipFile):self.docs.file(self.cid,item['id'])
  self.assertEqual(self.docs.original(self.cid,item['id']),p)
 def test_path_only_reference_and_image_label_classification(self):
  folder=self.documents();(folder/'report.txt').write_text('Read me');(folder/'photo.png').write_bytes(fixtures.PNG);self.data['mapping']['n4']['message']['metadata']['attachments']=[dict(path='attachments/report.txt')];self.data['mapping']['n4']['message']['content']['parts']=['![Photo label](attachments/photo.png)'];self.save();items=self.docs.public(self.cid)['attachments'];self.assertEqual({i['kind'] for i in items},{'image','text'});self.assertTrue(all(i['seq']==4 for i in items))
 def test_document_relative_asset_requires_thread_provenance(self):
  folder=self.documents();(folder/'report.md').write_text('![Image](private.png)');(folder/'private.png').write_bytes(fixtures.PNG);self.data['mapping']['n4']['message']['content']['parts']=['[report](attachments/report.md)'];self.save();item=self.docs.public(self.cid)['attachments'][0]
  with self.assertRaises(FileNotFoundError):self.docs.relative(self.cid,item['id'],'private.png')
  self.data['mapping']['n4']['message']['content']['parts'].append('![Owned](attachments/private.png)');self.save();item=self.docs.public(self.cid)['attachments'][0];self.assertEqual(self.docs.relative(self.cid,item['id'],'private.png'),folder/'private.png')
 def test_cross_chat_downloaded_copy_requires_selection_and_persists(self):
  from preferences import attach
  folder=self.documents();attach(self.a,self.root/'preferences.json')
  (folder/'other').mkdir();copy=folder/'other/workspace (7)(4).md';copy.write_text('# Downloaded revision')
  (folder/'library-index.json').write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':[dict(id='copy-id',name=copy.name,path='attachments/other/'+copy.name,conversation_ids=['other-chat'])]}))
  self.data['mapping']['n4']['message']['content']['parts']=['[Workspace (7)(4)](sandbox:/workspace/scratch/Workspace_7_4.md)'];self.save()
  item=self.docs.public(self.cid)['attachments'][0];self.assertFalse(item['available']);self.assertEqual(len(item['candidates']),1)
  with self.assertRaises(ValueError):self.docs.link(self.cid,item['id'],'unrelated-key')
  self.docs.link(self.cid,item['id'],item['candidates'][0]['key']);item=self.docs.public(self.cid)['attachments'][0];self.assertTrue(item['available']);self.assertTrue(item['local_copy']);self.assertEqual(item['size'],copy.stat().st_size)
  with patch.object(self.files,'refresh',side_effect=AssertionError('No rescan during delivery')):self.assertEqual(self.docs.file(self.cid,item['id']),copy)
  self.assertTrue(json.loads((self.root/'preferences.json').read_text())['settings']['attachmentLinks'])
  recreated=ThreadAttachments(self.a,self.files);self.assertTrue(recreated.public(self.cid)['attachments'][0]['available'])
  copy.write_text('# Changed revision')
  item=recreated.public(self.cid)['attachments'][0];self.assertFalse(item['available']);self.assertTrue(item['candidates'])
 def test_repeated_sandbox_reference_preserves_original_filename_alias(self):
  folder=self.documents();path=folder/'canon_core_front_matter (9)(1).md';path.write_text('Downloaded canon')
  (folder/'library-index.json').write_text(json.dumps({'schema':'chatgpt-library-index/v1','entries':[dict(id='canon',name=path.name,path='attachments/'+path.name,conversation_ids=['another-chat'])]}))
  self.data['mapping']['n4']['message']['content']['parts']=['[Canon Organizer](sandbox:/scratch/Canon_Organizer.md)']
  self.data['mapping']['n240']['message']['content']['parts']=['[canon_core_front_matter (9)(1).md](sandbox:/scratch/Canon_Organizer.md)'];self.save()
  item=self.docs.public(self.cid)['attachments'][0];self.assertFalse(item['available']);self.assertEqual(item['candidates'][0]['name'],path.name)
 def test_parenthesized_markdown_destination_is_complete(self):
  folder=self.documents();path=folder/'report(7)(4).md';path.write_text('Saved')
  self.data['mapping']['n4']['message']['content']['parts']=['[Report](attachments/report(7)(4).md)'];self.save()
  item=self.docs.public(self.cid)['attachments'][0];self.assertTrue(item['available']);self.assertEqual(self.docs.file(self.cid,item['id']),path)
 def test_http_copy_and_attachment_require_session(self):
  folder=self.documents();(folder/'report.txt').write_text('actual bytes');self.data['mapping']['n4']['message']['content']['parts']=['[report](attachments/report.txt)'];self.save();server=Server(('127.0.0.1',0),self.a);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();c=http.client.HTTPConnection('127.0.0.1',server.server_port)
  try:
   route='/api/thread-attachments?id='+self.cid;c.request('GET',route);r=c.getresponse();self.assertEqual(r.status,403);r.read();cookie={'Cookie':server.cookie_name+'='+server.token};c.request('GET',route,headers=cookie);r=c.getresponse();item=json.loads(r.read())['attachments'][0];c.request('GET','/api/thread-attachments/content?id='+self.cid+'&attachment='+item['id'],headers=cookie);r=c.getresponse();self.assertEqual(r.status,200);self.assertEqual(r.read(),b'actual bytes');c.request('GET','/api/thread-markdown?id='+self.cid,headers=cookie);r=c.getresponse();self.assertEqual(r.getheader('X-Markdown-Source'),'generated');self.assertTrue(r.read().startswith(b'# '))
  finally:c.close();server.shutdown();server.server_close();thread.join()
 def test_sandbox_uses_only_nonce_authorized_bundled_scripts(self):
  self.documents();server=Server(('127.0.0.1',0),self.a);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();c=http.client.HTTPConnection('127.0.0.1',server.server_port)
  try:
   c.request('GET','/attachment-frame.html',headers={'Cookie':server.cookie_name+'='+server.token});r=c.getresponse();html=r.read().decode();policy=r.getheader('Content-Security-Policy');self.assertEqual(r.status,200);self.assertIn('sandbox allow-scripts;',policy);self.assertNotIn('allow-same-origin',policy);self.assertIn("connect-src 'none'",policy);self.assertNotIn('<script defer src=',html);self.assertEqual(html.count('<script nonce='),4);self.assertNotIn('http-equiv="Content-Security-Policy"',html)
  finally:c.close();server.shutdown();server.server_close();thread.join()
 def test_multiple_original_candidates_are_not_guessed(self):
  self.documents();manifest=self.root/'conversation-index.json';entry=dict(id=self.cid,json='chat.json',markdown='one.md');(self.root/'one.md').write_text('First original');(self.root/'two.md').write_text('Second original');manifest.write_text(json.dumps({'entries':[entry]}));self.a.register_manifest(entry,manifest,self.root)
  with self.a.connect() as db:db.execute('INSERT INTO manifest_entries VALUES(?,?,?,?,?)',(self.cid,str(self.root/'other-index.json'),json.dumps(dict(entry,markdown='two.md')),str(self.path),1))
  text,mode=thread_markdown(self.a,self.cid);self.assertEqual(mode,'generated');self.assertNotIn('First original',text)
