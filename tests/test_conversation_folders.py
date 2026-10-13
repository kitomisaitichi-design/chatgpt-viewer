import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from viewer import Archive
from native_codex import NativeCodex,conversation_metadata
from conversation_folders import resolve_folder,open_conversation_folder
from library_files import FileCatalog
from thread_attachments import ThreadAttachments

class ConversationFolders(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.home=self.root/'codex';self.folder=self.root/'Home folder Δ';self.folder.mkdir();self.a=Archive(self.root/'data',background_process=False)
 def tearDown(self):self.a.close();self.temp.cleanup()
 def session(self,cid='child',source=None,cwd=None):
  folder=self.home/'sessions/2026/10/13';folder.mkdir(parents=True,exist_ok=True);path=folder/(cid+'.jsonl')
  metadata=dict(id=cid,originator='codex_cli_rs',timestamp='2026-10-13T12:00:00Z',source=source or 'vscode',cwd=str(cwd or self.folder))
  text='[Open home](<'+str(self.folder)+'>)'
  path.write_text(json.dumps(dict(type='session_meta',payload=metadata))+'\n'+json.dumps(dict(type='response_item',payload=dict(type='message',role='assistant',content=[dict(type='output_text',text=text)])))+'\n',encoding='utf-8')
  with patch('native_codex.homes',return_value=[self.home]):NativeCodex(self.a).discover()
  return path
 def test_producer_metadata_distinguishes_agents_from_forks_and_titles(self):
  agent=conversation_metadata(dict(cwd=str(self.folder),source={'subagent':{'thread_spawn':{'parent_thread_id':'parent','agent_nickname':'Dirac'}}}))
  self.assertTrue(agent['is_subagent']);self.assertEqual(agent['parent_id'],'parent');self.assertEqual(agent['agent_nickname'],'Dirac')
  self.assertFalse(conversation_metadata(dict(title='subagent rollout',source='vscode',parent_thread_id='parent'))['is_subagent'])
  self.assertTrue(conversation_metadata(dict(source={'subagent':'review'}))['is_subagent'])
 def test_metadata_survives_lazy_discovery_message_loading_and_restart(self):
  self.a.enable_ui_cache();self.session(source={'subagent':{'thread_spawn':{'parent_thread_id':'parent'}}})
  before=self.a.catalog_batch()['chats'][0];self.assertTrue(before['is_subagent']);self.assertEqual(before['workspace'],str(self.folder));self.assertEqual(self.a.source_reader.reads,0)
  self.a.foreground_page('child');after=self.a.catalog()[0];self.assertTrue(after['is_subagent']);self.assertEqual(after['parent_id'],'parent')
  self.a.close();self.a=Archive(self.root/'data',background_process=False);reopened=self.a.catalog()[0];self.assertTrue(reopened['is_subagent']);self.assertEqual(reopened['workspace'],str(self.folder))
 def test_folder_targets_and_exact_link_validation(self):
  path=self.session();self.assertEqual(resolve_folder(self.a,'child'),self.folder);self.assertEqual(resolve_folder(self.a,'child','source'),path.parent)
  self.assertEqual(resolve_folder(self.a,'child','reference',str(self.folder)),self.folder)
  with self.assertRaises(ValueError):resolve_folder(self.a,'child','reference',str(self.root))
  with self.assertRaises(ValueError):resolve_folder(self.a,'child','other')
 def test_duplicate_lazy_manifests_keep_one_conversation(self):
  path=self.session(source={'subagent':'review'})
  self.a.register_manifest(dict(id='child',json=path.name,chat_kind='codex',workspace=str(self.folder),is_subagent=True),path.parent/'second-index.json',self.home)
  chats=self.a.catalog();self.assertEqual(len(chats),1);self.assertTrue(chats[0]['is_subagent'])
 def test_missing_folder_reports_failure_without_creating_it(self):
  missing=self.root/'Missing folder';self.session(cwd=missing)
  with self.assertRaises(FileNotFoundError):resolve_folder(self.a,'child')
  self.assertFalse(missing.exists())
 def test_open_uses_existing_folder_service(self):
  self.session()
  with patch('folder_tools.open_folder',return_value={'opened':True}) as opener:self.assertTrue(open_conversation_folder(self.a,'child')['opened'])
  opener.assert_called_once_with(self.folder)
 def test_linked_directory_is_a_folder_card_not_a_downloadable_file(self):
  self.session();docs=ThreadAttachments(self.a,FileCatalog(self.a));cards=docs.public('child')['attachments'];folder=next(c for c in cards if c['kind']=='folder')
  self.assertTrue(folder['available']);self.assertEqual(folder['folder_reference'],str(self.folder));self.assertIsNone(folder['size'])
  with self.assertRaises((OSError,ValueError)):docs.file('child',folder['id'])

if __name__=='__main__':unittest.main()
