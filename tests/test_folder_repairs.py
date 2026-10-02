import ctypes,json,os,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from atomic_files import atomic_bytes
from archive_backup import local_links,plan_files,BackupManager
from folder_tools import drive_suggestion,quick_setup,pick_folder,open_folder
from viewer import Archive

class FolderRepairs(unittest.TestCase):
    def test_parallel_progress_writers_keep_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'progress.json';errors=[]
            def write(index):
                try:
                    for n in range(12):atomic_bytes(p,json.dumps({'writer':index,'text':'x'*1000,'n':n}).encode())
                except Exception as e:errors.append(e)
            threads=[threading.Thread(target=write,args=(i,)) for i in range(4)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertFalse(errors);self.assertEqual(len(json.loads(p.read_text())['text']),1000)
            self.assertEqual(list(Path(directory).iterdir()),[p])
    def test_failed_replace_preserves_existing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'progress.json';p.write_bytes(b'old')
            with patch('atomic_files.os.replace',side_effect=PermissionError('locked')),patch('atomic_files.time.sleep'):
                with self.assertRaisesRegex(PermissionError,'completed ZIPs are kept'):atomic_bytes(p,b'new')
            self.assertEqual(p.read_bytes(),b'old');self.assertEqual(list(Path(directory).iterdir()),[p])
    @unittest.skipUnless(os.name=='nt','Windows sharing semantics')
    def test_live_windows_reader_lock_retries_successfully(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'progress.json';p.write_bytes(b'old');kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p];kernel.CreateFileW.restype=ctypes.c_void_p
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            handle=kernel.CreateFileW(str(p),0x80000000,1,None,3,0,None);self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            timer=threading.Timer(.12,lambda:kernel.CloseHandle(handle));timer.start()
            try:atomic_bytes(p,b'new');self.assertEqual(p.read_bytes(),b'new')
            finally:timer.join()
    def test_drive_preference_and_detection_does_not_create_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            g=Path(directory)/'G';h=Path(directory)/'H';(g/'My Drive').mkdir(parents=True);(h/'My Drive').mkdir(parents=True)
            result=drive_suggestion([g,h]);self.assertEqual(result['root'],str(g/'My Drive'));self.assertFalse(Path(result['sync_folder']).exists())
            self.assertEqual(drive_suggestion([h])['root'],str(h/'My Drive'));self.assertFalse(drive_suggestion([Path(directory)/'empty'])['available'])
    def test_quick_scan_preserves_selected_loader_and_depth(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);selected=base/'chosen';selected.mkdir();other=base/'downloads/CHATGPT/chatgpt-backup';(other/'markdown').mkdir(parents=True);(other/'json').mkdir()
            result=quick_setup({'scan_start':str(selected),'scan_up':3},base/'app',downloads=base/'downloads')
            self.assertEqual(result['source'],str(selected));self.assertEqual(result['up'],3);self.assertIn(str(other),result['source_candidates'])
            self.assertEqual(quick_setup({},base/'app',downloads=base/'downloads')['source'],str(other))
    @unittest.skipUnless(os.name=='nt','Windows shell')
    def test_open_local_uses_shell_without_saving_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            a=Archive(Path(directory)/'data',background_process=False);manager=BackupManager(a,Path(directory)/'app')
            try:
                with patch('folder_tools.os.startfile') as shell,patch('archive_backup.write_json',side_effect=PermissionError('settings locked')):
                    result=manager.open_local(str(Path(directory)/'My ZIPs'));shell.assert_called_once_with(result['path'],'open');self.assertTrue(result['opened']);self.assertTrue(Path(result['path']).is_dir())
            finally:manager.close();a.close()
    @unittest.skipUnless(os.name=='nt','Windows common dialog')
    def test_modern_picker_initializes_native_com_at_existing_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            result=pick_folder(str(Path(directory)/'not-created-yet'),show=False);self.assertTrue(result['initialized']);self.assertEqual(result['initial'],directory)
    def test_unmatched_code_brackets_do_not_stall_attachment_scan(self):
        started=time.monotonic();self.assertEqual(local_links('['*300000+'\n"foo"'),set());self.assertLess(time.monotonic()-started,1)
    def test_cached_references_invalidate_changes_and_recheck_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);doc=root/'chat.md';(root/'attachments').mkdir();asset=root/'attachments/image.png';asset.write_bytes(b'image');doc.write_text('![x](attachments/image.png)')
            cache={};files,*_=plan_files(root,documents=[doc],reference_cache=cache);self.assertIn('attachments/image.png',files)
            with patch('archive_backup.local_links',side_effect=AssertionError('unchanged text should use cached links')):
                files,*_=plan_files(root,documents=[doc],reference_cache=cache);self.assertIn('attachments/image.png',files)
            asset.unlink();files,_,missing=plan_files(root,documents=[doc],reference_cache=cache);self.assertNotIn('attachments/image.png',files);self.assertTrue(missing)
            doc.write_text('No image now');_,_,missing=plan_files(root,documents=[doc],reference_cache=cache);self.assertFalse(missing)

if __name__=='__main__':unittest.main()
