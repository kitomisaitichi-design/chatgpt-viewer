import json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from archive_backup import BackupManager,BackupIntegrityError,digest
from selected_backup import prepare,preview,create
from drive_backup import save_private
from viewer import Archive

class SelectedBackups(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.a=Archive(self.root/'data',background_process=False);self.m=BackupManager(self.a,Path(__file__).parents[1]);self.source=self.root/'source';self.source.mkdir();self.output=self.root/'backups';self.m.save_config(dict(source=str(self.source),local_folder=str(self.output),cleanup_extras=False))
  (self.source/'assets').mkdir();(self.source/'assets/note.txt').write_text('Linked source');self.raw=[dict(id=cid,title=title,create_time=100,update_time=200,messages=[dict(role='user',content=text)],preserved=dict(citations=['saved-source'],branches=['first','second'])) for cid,title,text in [('chat-a-12345678','First','| A | B |\n|---|---|\n| 1 | 2 |\n\n```python\nprint(1)\n```\n[Note](assets/note.txt)'),('chat-b-12345678','Second','PRIVATE UNSELECTED CHAT')]]
  self.path=self.source/'shared.json';self.path.write_text(json.dumps(self.raw))
  for item in self.a.read_items(self.path):self.a.store(item,self.path,'fp',self.source,{})
 def tearDown(self):self.m.close();self.a.close();self.temp.cleanup()
 def job(self,ids=None,formats=None):return dict(ids=ids or ['chat-a-12345678'],formats=formats or ['markdown','json','files'],destination=str(self.output))
 def test_preview_is_read_only_and_shared_json_is_scoped_to_selected_chat(self):
  original=self.path.read_bytes();before=list(self.output.iterdir()) if self.output.exists() else [];p=preview(self.a,['chat-a-12345678']);self.assertEqual(p['ids'],['chat-a-12345678']);self.assertEqual(p['shared_sources'],1);self.assertEqual(p['attachments'],1);self.assertEqual(list(self.output.iterdir()) if self.output.exists() else [],before);self.assertEqual(self.path.read_bytes(),original)
 def test_selected_zip_preserves_structure_formatting_and_linked_asset(self):
  receipt=create(self.m,self.job());self.assertEqual(digest(receipt['path'])[0],receipt['sha256'])
  with zipfile.ZipFile(receipt['path']) as z:
   self.assertIsNone(z.testzip());index=json.loads(z.read('archive-index.json'));self.assertEqual([c['id'] for c in index['conversations']],['chat-a-12345678']);raw=json.loads(z.read('archive/'+index['conversations'][0]['json'][0]));self.assertEqual(raw['preserved'],self.raw[0]['preserved']);self.assertNotIn('PRIVATE UNSELECTED',json.dumps(raw));self.assertEqual(z.read('archive/'+index['conversations'][0]['attachments'][0]),b'Linked source');markdown=z.read('archive/'+index['conversations'][0]['markdown'][0]).decode();self.assertIn('| A | B |',markdown);self.assertIn('```python',markdown)
  other=Archive(self.root/'restored',background_process=False);manager=BackupManager(other,Path(__file__).parents[1])
  try:manager.import_zip(receipt['path']);manager.worker.join(5);self.assertEqual([c['id'] for c in other.catalog()],['chat-a-12345678']);self.assertEqual(other.foreground_page('chat-a-12345678')['total'],1)
  finally:manager.close();other.close()
 def test_exact_ids_required_and_unknown_chat_rejected(self):
  for ids in ([],['unknown'],['chat-a-12345678',123]):
   with self.assertRaises(ValueError):preview(self.a,ids)
  with self.assertRaises(ValueError):preview(self.a,['chat-a-12345678'],['images'])
 def test_different_selections_are_not_coalesced_in_queue(self):
  with patch.object(self.m,'kick'):
   self.m.start_selected(['chat-a-12345678']);self.m.start_selected(['chat-a-12345678']);self.m.start_selected(['chat-b-12345678'])
  self.assertEqual(self.m.queue.status()['pending'],2)
 def test_selected_export_does_not_change_full_backup_slots_or_schedule(self):
  before=self.m.config();save_private(self.m.state_path,dict(slots={'full':{'sha256':'previous'}}));create(self.m,self.job());self.assertEqual(self.m.state()['slots']['full']['sha256'],'previous');self.assertEqual(self.m.config(),before)
 def test_changed_selected_zip_cannot_be_downloaded(self):
  receipt=create(self.m,self.job());self.assertEqual(str(self.m.selected_download(receipt['id'])),receipt['path']);Path(receipt['path']).write_bytes(b'changed')
  with self.assertRaises(BackupIntegrityError):self.m.selected_download(receipt['id'])
 def test_destination_change_requires_another_preview(self):
  with self.assertRaisesRegex(ValueError,'folder changed'):self.m.start_selected(['chat-a-12345678'],destination=str(self.root/'different'))
  self.assertEqual(self.m.queue.status()['pending'],0)
 def test_native_selected_backup_restores_subagent_metadata(self):
  from native_codex import conversation_metadata
  path=self.source/'native.jsonl';cid='native-12345678';header=dict(id=cid,title='Agent',originator='codex_cli_rs',cwd=str(self.source),source={'subagent':{'thread_spawn':{'parent_thread_id':'parent','agent_nickname':'Dirac'}}})
  path.write_text(json.dumps(dict(type='session_meta',payload=header))+'\n'+json.dumps(dict(type='response_item',payload=dict(type='message',role='user',content=[dict(type='input_text',text='Native content')]))))
  self.a.register_manifest(dict(id=cid,json=path.name,chat_kind='codex',**conversation_metadata(header)),self.source/'native-index.json',self.source)
  receipt=create(self.m,self.job([cid],['json']));other=Archive(self.root/'native-restored',background_process=False);manager=BackupManager(other,Path(__file__).parents[1])
  try:manager.import_zip(receipt['path']);manager.worker.join(5);chat=other.catalog()[0];self.assertTrue(chat['is_subagent']);self.assertEqual(chat['parent_id'],'parent');self.assertEqual(other.foreground_page(cid)['total'],1)
  finally:manager.close();other.close()
  markdown_receipt=create(self.m,self.job([cid],['markdown']));other=Archive(self.root/'native-markdown-restored',background_process=False);manager=BackupManager(other,Path(__file__).parents[1])
  try:manager.import_zip(markdown_receipt['path']);manager.worker.join(5);chat=other.catalog()[0];self.assertTrue(chat['is_subagent']);self.assertEqual(chat['parent_id'],'parent');self.assertEqual(other.foreground_page(cid)['total'],1)
  finally:manager.close();other.close()

if __name__=='__main__':unittest.main()
