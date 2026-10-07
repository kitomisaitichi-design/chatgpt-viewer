import json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from native_connection import NativeConnection


class NativeConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.browser=SimpleNamespace(archive=SimpleNamespace(data_dir=self.root),statuses=lambda:[],reset=Mock(),endpoint='http://127.0.0.1:23456',secret='fixture-only')
        self.native=NativeConnection(self.browser)
    def tearDown(self):self.temp.cleanup()

    def test_double_connect_reuses_one_owned_process(self):
        def start(show):
            self.native.process=Mock();self.native.process.poll.return_value=None
            self.native.write('native-connection-state.json',dict(phase='sign-in'))
        with patch.object(self.native,'_start',side_effect=start) as launch:
            workers=[threading.Thread(target=self.native.connect) for _ in range(2)]
            for w in workers:w.start()
            for w in workers:w.join()
            self.assertEqual(launch.call_count,1)
        command=json.loads((self.root/'native-connection-control.json').read_text())
        self.assertTrue(command['show']);self.assertTrue(self.native.enabled.exists())

    def test_process_or_state_file_cannot_fake_authentication(self):
        self.native.write('native-connection-state.json',dict(phase='connected'))
        self.assertFalse(self.native.status()['connected'])
        self.native.process=Mock();self.native.process.poll.return_value=None
        self.assertFalse(self.native.status()['connected'])
        self.browser.statuses=lambda:[dict(version='native',connected=True)]
        self.assertTrue(self.native.status()['connected'])
        self.native.process.poll.return_value=1
        self.assertFalse(self.native.status()['connected'])

    def test_connected_account_button_does_not_reset_or_restart(self):
        self.native.process=Mock();self.native.process.poll.return_value=None
        self.browser.statuses=lambda:[dict(version='native',connected=True)]
        with patch.object(self.native,'_start') as launch:self.native.connect();launch.assert_not_called()
        self.browser.reset.assert_not_called()
        self.assertFalse(json.loads((self.root/'native-connection-control.json').read_text())['reset'])

    def test_blocked_retry_budget_does_not_auto_restart(self):
        self.native.write(self.native.enabled.name,dict(enabled=True))
        self.native.write('native-connection-state.json',dict(phase='blocked',attempts=3))
        with patch.object(NativeConnection,'_start') as launch:
            restored=NativeConnection(self.browser);launch.assert_not_called()
        self.assertEqual(restored.status()['phase'],'blocked')


if __name__=='__main__':unittest.main()
