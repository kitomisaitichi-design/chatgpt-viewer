import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnose_viewer import diagnose, probe, session_target


class Checks(unittest.TestCase):
    def test_rejects_nonlocal_and_invalid_sessions(self):
        for url in ('https://example.com/?token=secret', 'http://127.0.0.1.example.com:4/?token=secret',
                    'http://user@127.0.0.1:4/?token=secret', 'http://127.0.0.1:4/?token=bad%0Avalue'):
            with self.assertRaises(ValueError):
                session_target({'url': url})

    def test_missing_session_still_produces_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = diagnose(Path(tmp))
            self.assertEqual(report['finding'], 'session_unavailable')
            self.assertFalse(report['database']['exists'])


class HTTPChecks(unittest.TestCase):
    def setUp(self):
        self.mode = 'ok'
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.headers.get('Cookie') != 'viewer_token=TEST_SECRET':
                    self.send_error(403)
                    return
                if owner.mode == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', '/redirect-must-not-be-followed')
                    self.end_headers()
                    return
                if self.path == '/api/state' and owner.mode == 'stall':
                    time.sleep(.25)
                data = {'ok': True, 'version': '1.0.3', 'pid': 123} if self.path == '/api/health' else {
                    'chats': [{'title': 'PRIVATE_CHAT', 'text': 'PRIVATE_MESSAGE'}], 'revision': 7,
                    'settings': {'scan_start': 'PRIVATE_PATH'}, 'coverage': {'available': 1},
                    'scan': {'errors': ['PRIVATE_PATH']}}
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name)
        self.data = self.app / '.viewer-data'
        self.data.mkdir()
        (self.app / 'viewer.py').write_text("version='1.0.3'", encoding='utf-8')
        (self.data / 'session.json').write_text(json.dumps({'url': self.base + '/?token=TEST_SECRET', 'pid': 123}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_live_status_and_private_fields_removed(self):
        report = diagnose(self.app)
        self.assertEqual(report['finding'], 'status_responds_outside_browser')
        self.assertEqual(report['requests'][1]['returned_chats'], 1)
        serialized = json.dumps(report)
        for secret in ('TEST_SECRET', 'PRIVATE_CHAT', 'PRIVATE_MESSAGE', 'PRIVATE_PATH'):
            self.assertNotIn(secret, serialized)

    def test_stalled_state_distinguished_from_dead_server(self):
        self.mode = 'stall'
        report = diagnose(self.app, timeout=.05)
        self.assertEqual(report['finding'], 'server_alive_but_status_request_stalls')
        self.assertEqual(report['requests'][-1]['outcome'], 'ok')

    def test_old_running_version_is_detected(self):
        (self.app / 'viewer.py').write_text("version='1.0.4'", encoding='utf-8')
        self.assertEqual(diagnose(self.app)['finding'], 'running_server_version_differs_from_files')

    def test_rejected_session_and_redirects_are_reported(self):
        self.assertEqual(probe(self.base, 'WRONG', '/api/health')['http_status'], 403)
        self.mode = 'redirect'
        self.assertEqual(probe(self.base, 'TEST_SECRET', '/api/health')['http_status'], 302)


if __name__ == '__main__':
    unittest.main()
