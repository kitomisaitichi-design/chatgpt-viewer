import json, os, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from viewer import Archive
from preferences import attach
from library_files import FileCatalog
from thread_images import ThreadImages
from thread_attachments import ThreadAttachments
from source_reader import native_conversation
from native_codex import NativeCodex
from deletion_queue import DeletionQueue, SCHEMA, read, write
from test_thread_images import PNG

class CollectionsNative(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.a=Archive(self.root/'data',background_process=False);self.q=None
 def tearDown(self):
  if self.q:self.q.close()
  self.a.close();self.temp.cleanup()
 def chat(self,cid='12345678-1234-1234-1234-123456789abc'):
  p=self.root/(cid+'.json');p.write_text(json.dumps(dict(id=cid,title='Saved chat',messages=[dict(role='user',content='Read me')])));item=next(self.a.read_items(p));self.a.store(item,p,'fingerprint',self.root,{})
  manifest=self.root/'conversation-index.json';entry=dict(id=cid,json=p.name,content_hash='original-exporter-hash');write(manifest,dict(scope='account:workspace',entries=[entry]));self.a.register_manifest(entry,manifest,self.root);return cid,p
 def queue(self):
  self.q=DeletionQueue(self.a,FileCatalog(self.a));return self.q
 def run_queue(self,q):
  # Tick deterministically; production uses its background thread.
  with patch.object(q,'start'):q.action('run',[r['id'] for r in q.rows()])
  q.tick();return q.rows()[0]
 def receipt(self,row,**extra):
  write(self.root/'.viewer-queue/receipts'/(row['id']+'.json'),dict(schema=SCHEMA,id=row['id'],cid=row['cid'],scope=row['scope'],run=row['run'],state='confirmed',verified=True,**extra))
 def test_bookmarks_and_manual_kind_persist_after_reindex_and_version_migration(self):
  cid,p=self.chat();profile=self.root/'preferences.json';attach(self.a,profile);self.a.organize(cid,dict(bookmarked=1,kind_override='codex'));item=next(self.a.read_items(p));self.a.store(item,p,'new',self.root,{})
  c=self.a.catalog()[0];self.assertEqual((c['bookmarked'],c['kind_override']),(1,'codex'));b=Archive(self.root/'other',background_process=False)
  try:
   attach(b,profile)
   with b.connect() as db:r=db.execute('SELECT bookmarked,kind_override FROM organization WHERE cid=?',(cid,)).fetchone()
   self.assertEqual(tuple(r),(1,'codex'));self.assertEqual(c['kind'],'chat')
  finally:b.close()
 def test_queue_dedup_review_backups_and_receipt(self):
  cid,p=self.chat();q=self.queue();q.enqueue([cid]);q.enqueue([cid]);self.assertEqual(len(q.rows()),1)
  with self.assertRaises(ValueError):q.action('run',[])
  row=self.run_queue(q);self.assertTrue(read(self.root/'.viewer-queue/control.json')['enabled']);self.assertEqual(q.rows()[0]['state'],'waiting');self.assertTrue((self.a.data_dir/'deletion-recovery'/row['id']/'conversation.md').is_file())
  command=read(self.root/'.viewer-queue/commands'/(row['id']+'.json'));self.assertEqual(command['content_hash'],'original-exporter-hash')
  with self.assertRaises(ValueError):q.action('run',[row['id']])
  self.receipt(row);q.tick();self.assertEqual(q.rows()[0]['state'],'confirmed');self.assertTrue(self.a.catalog()[0]['trashed']);self.assertTrue(p.is_file());q.enqueue([cid]);self.assertEqual(len(q.rows()),1)
 def test_unverified_wrong_account_and_stale_receipts_cannot_finalize(self):
  cid,_=self.chat();q=self.queue();q.enqueue([cid]);row=self.run_queue(q);receipt=dict(schema=SCHEMA,id=row['id'],cid=cid,scope='wrong',run=row['run'],state='confirmed',verified=True);path=self.root/'.viewer-queue/receipts'/(row['id']+'.json');write(path,receipt);q.tick();self.assertEqual(q.rows()[0]['state'],'waiting')
  receipt['scope']=row['scope'];receipt['verified']=False;write(path,receipt);q.tick();self.assertEqual(q.rows()[0]['state'],'waiting')
  receipt['verified']=True;receipt['run']='old-run';write(path,receipt);q.tick();self.assertEqual(q.rows()[0]['state'],'waiting')
 def test_unavailable_is_not_deleted_and_never_cleans_local_library(self):
  cid,p=self.chat();q=self.queue();q.enqueue([cid]);row=self.run_queue(q)
  with patch.object(q,'cleanup') as cleanup:self.receipt(row,remote_state='unavailable');q.tick();cleanup.assert_not_called()
  chat=self.a.catalog()[0];self.assertEqual(chat['remote_state'],'unavailable');self.assertFalse(chat['trashed']);self.assertTrue(p.is_file())
  self.assertFalse((self.root/'.viewer-queue/commands'/(row['id']+'.json')).exists());self.assertTrue((self.root/'.viewer-queue/history'/row['run']/(row['id']+'.json')).exists())
  q.close();self.q=DeletionQueue(self.a,FileCatalog(self.a));self.assertEqual(self.a.catalog()[0]['remote_state'],'unavailable')
 def test_status_receipt_scope_unknown_and_changed_hash(self):
  cid,p=self.chat();q=self.queue()
  with patch.object(q,'start'):request=q.check_remote(cid)
  check=read(self.root/'.viewer-queue/checks'/(cid+'.json'));target=self.root/'.viewer-queue/check-receipts'/(request['id']+'.json')
  receipt=dict(check,state='deleted',verified=True,checked=123,scope='wrong');write(target,receipt);q.collect_checks();self.assertNotIn('remote_state',self.a.catalog()[0])
  receipt.update(scope=check['scope'],state='unknown',verified=False);write(target,receipt);q.collect_checks();self.assertNotIn('remote_state',self.a.catalog()[0])
  receipt.update(state='deleted',verified=True);write(target,receipt);q.collect_checks();self.assertEqual(self.a.catalog()[0]['remote_state'],'deleted')
  self.assertEqual(read(self.root/'conversation-index.json')['entries'][0]['content_hash'],'original-exporter-hash');self.assertTrue(p.is_file())
 def test_status_cache_and_two_retry_reset_nonce(self):
  cid,_=self.chat();q=self.queue()
  with patch.object(q,'start'):
   first=q.check_remote(cid);self.assertEqual(first,q.check_remote(cid));q.reconnect()
  self.assertTrue(read(self.root/'.viewer-queue/reconnect.json')['nonce'])
  write(self.root/'.viewer-queue/bridge.json',dict(scope='account:workspace',connected=False,connection=dict(blocked=True,attempts=3)))
  self.assertTrue(q.check_remote(cid)['blocked']);self.assertFalse(q.status()['bridges'][0]['connected'])
 def test_retention_mode_changes_only_before_execution(self):
  cid,_=self.chat();q=self.queue();q.enqueue([cid]);q.enqueue([cid],mode='preserve');self.assertEqual(q.rows()[0]['mode'],'preserve');row=self.run_queue(q)
  with self.assertRaises(ValueError):q.enqueue([cid],mode='library')
  self.assertEqual(q.rows()[0]['mode'],'preserve');self.receipt(row);q.tick();self.assertEqual(self.a.catalog()[0]['remote_state'],'deleted')
 def test_scoped_heartbeat_expires_and_index_tombstone_imports(self):
  cid,_=self.chat();q=self.queue();path=self.root/'.viewer-queue/bridge.json'
  import time
  write(path,dict(scope='account:workspace',connected=True,updated=time.time()));self.assertTrue(q.status()['bridges'][0]['connected'])
  write(path,dict(scope='wrong',connected=True,updated=time.time()));self.assertFalse(q.status()['bridges'][0]['connected'])
  write(path,dict(scope='account:workspace',connected=True,updated=time.time()-60));self.assertFalse(q.status()['bridges'][0]['connected'])
  entry=read(self.root/'conversation-index.json')['entries'][0];entry.update(deletion_verified=True,remote_deleted_at=time.time()*1000);write(self.root/'conversation-index.json',dict(scope='account:workspace',entries=[entry]));self.a.register_manifest(entry,self.root/'conversation-index.json',self.root);self.assertEqual(self.a.catalog()[0]['remote_state'],'deleted')
 def test_restart_pauses_and_stop_keeps_jobs(self):
  cid,_=self.chat();q=self.queue();q.enqueue([cid]);row=self.run_queue(q);q.close();q=DeletionQueue(self.a,FileCatalog(self.a));self.q=q;self.assertEqual(q.rows()[0]['state'],'paused');self.assertFalse(read(self.root/'.viewer-queue/control.json')['enabled']);q.action('stop');self.assertEqual(len(q.rows()),1)
 def test_crash_during_backup_and_unavailable_control_folder(self):
  cid,_=self.chat();q=self.queue();q.enqueue([cid])
  with patch.object(q,'start'):q.action('run',[q.rows()[0]['id']])
  q.close();q=DeletionQueue(self.a,FileCatalog(self.a));self.q=q;self.assertEqual(q.rows()[0]['state'],'paused')
  with patch('deletion_queue.write',side_effect=PermissionError('disconnected')):q.control(False)
  self.assertIn('folder unavailable',q.rows()[0]['error'])
 def test_shared_library_copy_survives_and_unshared_has_recovery(self):
  cid,_=self.chat();folder=self.root/'attachments';folder.mkdir();shared=folder/'shared.txt';shared.write_text('shared');single=folder/'single.txt';single.write_text('single')
  write(folder/'library-index.json',dict(schema='chatgpt-library-index/v1',entries=[dict(id='shared',path='attachments/shared.txt',name='shared.txt',conversation_ids=[cid,'other-chat']),dict(id='single',path='attachments/single.txt',name='single.txt',conversation_ids=[cid])]))
  q=self.queue();q.enqueue([cid]);row=self.run_queue(q);self.receipt(row);q.tick();self.assertTrue(shared.is_file());self.assertFalse(single.exists());index=read(self.a.data_dir/'deletion-recovery'/row['id']/'index.json');self.assertTrue(all(Path(f['copy']).is_file() for f in index['files']))
 def test_backup_failure_sends_no_executable_command(self):
  cid,_=self.chat();q=self.queue();q.enqueue([cid])
  with patch.object(q,'snapshot',side_effect=OSError('disk full')):row=self.run_queue(q)
  self.assertEqual(row['state'],'failed');self.assertFalse(read(self.root/'.viewer-queue/control.json')['enabled']);self.assertFalse((self.root/'.viewer-queue/commands'/(row['id']+'.json')).exists())
 def native(self,partial=False):
  home=self.root/'codex';folder=home/'sessions/2026/10/07';folder.mkdir(parents=True);p=folder/'rollout.jsonl';image=self.root/'photo.png';image.write_bytes(PNG);doc=self.root/'notes.md';doc.write_text('# Notes')
  records=[dict(type='session_meta',payload=dict(id='native-12345678',originator='codex_cli_rs',timestamp='2026-10-07T12:00:00Z')),dict(type='response_item',timestamp='2026-10-07T12:00:01Z',payload=dict(type='message',role='user',content=[dict(type='input_text',text='[Notes](<'+str(doc)+'>)'),dict(type='input_image',image_url=image.as_uri())])),dict(type='response_item',payload=dict(type='message',role='assistant',phase='final_answer',content=[dict(type='output_text',text='Answer')]))]
  p.write_text('\n'.join(json.dumps(r) for r in records)+'\n'+('{"type":' if partial else ''));return home,p,image,doc
 def test_native_discovery_is_lazy_validated_and_uses_state_title(self):
  home,p,_,_=self.native();db=sqlite3.connect(home/'state_5.sqlite');db.execute('CREATE TABLE threads(id,title,rollout_path)');db.execute('INSERT INTO threads VALUES(?,?,?)',('native-12345678','Native title',str(p)));db.commit();db.close();(p.parent/'bad.jsonl').write_text('{"type":"not-codex"}')
  with patch('native_codex.homes',return_value=[home]):n=NativeCodex(self.a);n.discover()
  catalog=self.a.catalog();self.assertEqual(len(catalog),1);self.assertEqual(catalog[0]['title'],'Native title');self.assertFalse(catalog[0]['loaded']);self.assertEqual(self.a.source_reader.reads,0);page=self.a.foreground_page(catalog[0]['id']);self.assertEqual(page['total'],2)
 def test_native_partial_tail_images_documents_and_authorization(self):
  home,p,image,doc=self.native(True);raw=native_conversation(p.read_text(),p);item=next(self.a.read_items(p));self.a.store(item,p,'fp',home,{})
  files=FileCatalog(self.a);images=ThreadImages(self.a,files);docs=ThreadAttachments(self.a,files);photo=images.public(item['id'])['images'][0];self.assertTrue(photo['available']);self.assertEqual(images.file(item['id'],photo['id']),image);self.assertTrue(any(d['available'] and d['kind']=='markdown' for d in docs.public(item['id'])['attachments']))
  private=self.root/'unlinked.txt';private.write_text('no access')
  with self.assertRaises(FileNotFoundError):self.a.asset(item['id'],str(private))
  self.assertEqual(raw['messages'][1]['channel'],'final_answer')
 def test_malformed_interior_and_fake_jsonl_rejected(self):
  _,p,_,_=self.native();p.write_text(p.read_text().replace('\n','\nnot JSON\n',1))
  with self.assertRaises(ValueError):native_conversation(p.read_text(),p)
  p.write_text('{"type":"session_meta","payload":{"id":"fake"}}\n')
  with self.assertRaises(ValueError):native_conversation(p.read_text(),p)

if __name__=='__main__':unittest.main()
