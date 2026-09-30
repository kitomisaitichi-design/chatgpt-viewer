import sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import setup_semantic
from viewer import Archive

class PortableSemanticTests(unittest.TestCase):
    def test_commands_use_current_python_local_target_and_cpu_wheels(self):
        target=Path('private-packages');args=setup_semantic.pip_command(target,'torch',index='https://download.pytorch.org/whl/cpu')
        self.assertEqual(args[0],sys.executable);self.assertIn('--target',args);self.assertIn('--only-binary=:all:',args);self.assertIn('https://download.pytorch.org/whl/cpu',args);self.assertNotIn('venv',args)
    def test_bundled_runtime_resolves_sibling_helpers(self):
        root=Path(setup_semantic.__file__).resolve().parent
        entries=(root/'runtime/python313._pth').read_text().splitlines()
        self.assertIn('..',entries)
        with zipfile.ZipFile(root/'runtime/pip.pyz') as z:self.assertIn('__main__.py',z.namelist());self.assertIsNone(z.testzip())
    def test_private_packages_win_over_older_system_packages(self):
        before=sys.path[:]
        try:
            with tempfile.TemporaryDirectory() as d:
                setup_semantic.activate(Path(d))
                self.assertEqual(sys.path[0],str(Path(d).resolve()))
        finally:sys.path[:]=before

    def test_cpp_runtime_is_bundled_for_clean_windows(self):
        root=Path(setup_semantic.__file__).resolve().parent/'runtime'
        for name in ('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'):
            self.assertEqual((root/name).read_bytes()[:2],b'MZ')
        self.assertTrue((root/'MSVC-LICENSE.rtf').is_file())

    def test_semantic_choice_starts_setup_without_blocking_search(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(d,background_process=False)
            try:
                with patch.object(a,'request_semantic') as start:
                    result=a.search('weather','semantic');start.assert_called_once();self.assertIn('background',result['notice']);self.assertEqual(result['mode'],'smart (text + related words)')
            finally:a.close()
    def test_setup_failure_unlocks_controls_and_retains_archive(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(d,background_process=False)
            try:
                with patch('viewer.subprocess.Popen',side_effect=OSError('offline test')):a.build_semantic()
                self.assertFalse(a.semantic_state['building']);self.assertFalse(a.semantic_state['ready']);self.assertIn('offline test',a.semantic_state['error']);self.assertTrue(a.semantic_lock.acquire(False));a.semantic_lock.release()
                self.assertIsInstance(a.catalog(),list)
            finally:a.close()
