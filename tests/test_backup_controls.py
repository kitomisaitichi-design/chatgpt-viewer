import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from archive_backup import build_zip,plan_files,BackupManager,BackupIntegrityError
from drive_backup import save_private
from viewer import Archive

class BackupControls(unittest.TestCase):
 def test_cancel_during_final_hash_preserves_previous_completed_zip(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);(root/'chat.md').write_text('# Saved chat');files,_,_=plan_files(root);target=root/'backup.zip';target.write_bytes(b'previous verified ZIP')
   with patch('archive_backup.digest',side_effect=InterruptedError('Cancelled during hash')):
    with self.assertRaises(InterruptedError):build_zip(root,target,files,dict(mode='full',files=files))
   self.assertEqual(target.read_bytes(),b'previous verified ZIP')
 def test_integrity_failure_pauses_retry_and_rebuild_requires_new_delivery_approval(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);source=root/'exports';source.mkdir();(source/'chat.md').write_text('# Chat\n## You\nSaved text');archive=Archive(root/'data',background_process=False);manager=BackupManager(archive,Path(__file__).parents[1])
   try:
    manager.save_config(dict(source=str(source),sync_folder=str(root/'mirror'),cleanup_extras=False));manager.run(False);state=manager.state();modes=['full','progress'];state['delivery_pending']=dict(destination='desktop:'+manager.config()['sync_folder'],modes=modes,fingerprint=state['local_fingerprint'],slots={mode:{k:state['slots'][mode][k] for k in ('path','sha256')} for mode in modes});save_private(manager.state_path,state)
    manager.local_path('full').write_bytes(b'changed')
    with patch.object(manager,'ready',return_value=True),patch('archive_backup.digest',side_effect=AssertionError('Size mismatch must reject without rehashing')):
     with self.assertRaises(BackupIntegrityError):manager.resume_delivery()
    self.assertTrue(manager.state()['delivery_pending']['paused']);self.assertTrue(manager.state()['delivery_pending']['needs_rebuild']);self.assertEqual(manager.status()['files']['full']['integrity'],'changed')
    with self.assertRaises(ValueError):manager.retry_delivery()
    (source/'chat.md').write_text('# Chat\n## You\nUpdated local content');manager.run(False);self.assertTrue(manager.status()['files']['full']['verified']);self.assertFalse(manager.state()['delivery_pending']['needs_rebuild']);self.assertTrue(manager.state()['delivery_pending']['needs_approval'])
    with self.assertRaisesRegex(ValueError,'approve'):manager.retry_delivery()
   finally:manager.close();archive.close()

if __name__=='__main__':unittest.main()
