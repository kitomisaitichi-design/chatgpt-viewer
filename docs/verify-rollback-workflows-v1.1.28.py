#!/usr/bin/env python3
r"""Smoke-test restored read, scan, Trash, restore, and local delete workflows.

Run from the project root:
    runtime\python.exe -B docs\verify-rollback-workflows-v1.1.28.py

All source exports and the SQLite database live in one TemporaryDirectory.
The only HTTP server binds to an ephemeral 127.0.0.1 port. No personal
archives, installed viewer data, network services, or release actions are used.
"""

import http.cookiejar
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import native_codex
from viewer import Archive, Server


def export(cid, title, prompt, answer):
    nodes = {}
    for index, (role, text) in enumerate((('user', prompt), ('assistant', answer))):
        key = f'node-{index}'
        nodes[key] = {
            'id': key,
            'parent': f'node-{index - 1}' if index else None,
            'children': [f'node-{index + 1}'] if index == 0 else [],
            'message': {
                'author': {'role': role},
                'content': {'content_type': 'text', 'parts': [text]},
                'create_time': 100 + index,
            },
        }
    return {'id': cid, 'title': title, 'mapping': nodes, 'current_node': 'node-1'}


def get(client, base, endpoint, **query):
    url = base + endpoint
    if query:
        url += '?' + urllib.parse.urlencode(query)
    with client.open(url, timeout=8) as response:
        assert response.status == 200, (endpoint, response.status)
        return json.load(response)


def post(client, base, endpoint, values):
    result = post_result(client, base, endpoint, values)
    assert result.get('ok') is True, (endpoint, result)


def post_result(client, base, endpoint, values):
    request = urllib.request.Request(
        base + endpoint,
        data=json.dumps(values).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with client.open(request, timeout=8) as response:
        result = json.load(response)
    assert 'error' not in result, (endpoint, result)
    return result


def chat(state, cid):
    return next((item for item in state['chats'] if item['id'] == cid), None)


def message_texts(client, base, cid):
    page = get(client, base, '/api/messages', id=cid, limit=20)
    assert page['total'] == 2, (cid, page)
    return [(item['role'], item['text']) for item in page['messages']]


def wait_for_scan(client, base, cid, timeout=35):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = get(client, base, '/api/state')
        if not last['scan']['scanning']:
            assert not last['scan']['errors'], last['scan']['errors']
            if chat(last, cid) is not None:
                return last
        time.sleep(0.1)
    raise AssertionError(f'Timed out discovering {cid}: {last["scan"] if last else "no status"}')


def wait_for_local_delete(client, base, job_id, timeout=22):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        status = get(client, base, '/api/delete-queue')
        last = next((item for item in status['jobs'] if item['id'] == job_id), None)
        assert last, 'Local delete job disappeared from the queue'
        if last['state'] == 'confirmed':
            return last, status
        if last['state'] == 'failed':
            raise AssertionError(f'Local delete failed: {last["error"]}')
        time.sleep(0.1)
    raise AssertionError(f'Local delete never confirmed: {last}')


def synthetic_native_session(cid, title, prompt, answer):
    records = [
        {'type': 'session_meta', 'payload': {
            'id': cid, 'title': title, 'originator': 'codex_cli',
            'timestamp': '2026-10-09T00:00:00Z',
        }},
        {'type': 'response_item', 'payload': {
            'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}],
        }},
        {'type': 'response_item', 'payload': {
            'role': 'assistant', 'content': [{'type': 'output_text', 'text': answer}],
        }},
    ]
    return ''.join(json.dumps(item) + '\n' for item in records).encode('utf-8')


def main():
    with tempfile.TemporaryDirectory(prefix='viewer-rollback-workflows-') as directory:
        home = Path(directory)
        source = home / 'synthetic-exports'
        source.mkdir()
        old_id, new_id = 'smoke-old-chat', 'smoke-new-chat'
        old_prompt = 'Please find uniquepersistedoldtoken in this old conversation.'
        old_answer = 'The old saved response survives the archive reload.'
        new_prompt = 'Please find uniquenewscantoken in this new conversation.'
        new_answer = 'The newly scanned export is readable.'
        old_file = source / 'old-chat.json'
        old_file.write_text(json.dumps(export(old_id, 'Previously saved chat', old_prompt, old_answer)), encoding='utf-8')
        # Override native discovery globally for this test process. Even when a
        # real CODEX_HOME exists, no native operation sees that personal root.
        fake_home = home / 'fake-codex-home'
        sessions = fake_home / 'sessions'
        sessions.mkdir(parents=True)

        native_homes_guard = patch.object(native_codex, 'homes', return_value=[fake_home])
        native_homes_guard.start()
        archive = None
        server = None
        try:
            archive = Archive(home / 'temporary-index', background_process=True)
            archive.scan(source, 0)
            assert not archive.status['errors'], archive.status['errors']
            assert {item['id'] for item in archive.catalog()} == {old_id}
            archive.enable_ui_cache()
            archive.cache_thread.join(timeout=8)
            assert archive.ui_cache and not archive.ui_cache['loading'], 'Initial catalog did not load'

            server = Server(('127.0.0.1', 0), archive)
            # A real Codex process running on the workstation must never
            # affect the fake session test; the path root guard remains live.
            server.native.deletion_queue.process_running = lambda: False
            server.native.deletion_queue.poll_interval = 0.1
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            client = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with client.open(base + '/?token=' + server.token, timeout=8) as response:
                response.read()

            first = get(client, base, '/api/state')
            assert chat(first, old_id) is not None, 'Previously indexed chat missing from sidebar state'
            assert message_texts(client, base, old_id) == [
                ('user', old_prompt), ('assistant', old_answer)
            ], 'Previously saved messages cannot be opened'
            print('PASS old chat: indexed catalog and both original messages readable')

            new_file = source / 'new-chat.json'
            new_file.write_text(json.dumps(export(new_id, 'Fresh export', new_prompt, new_answer)), encoding='utf-8')
            post(client, base, '/api/scan', {'path': str(source), 'up': 0})
            after_scan = wait_for_scan(client, base, new_id)
            assert chat(after_scan, old_id) is not None, 'Rescan lost the original chat'
            assert message_texts(client, base, new_id) == [
                ('user', new_prompt), ('assistant', new_answer)
            ], 'New export messages did not load'
            assert message_texts(client, base, old_id)[-1] == ('assistant', old_answer)
            print('PASS new export: HTTP scan discovered a second chat; original chat retained')

            post(client, base, '/api/organize', {'id': old_id, 'trashed': True})
            trashed = get(client, base, '/api/state')
            assert chat(trashed, old_id)['trashed'] == 1, 'Trash state did not persist in catalog'
            assert old_file.is_file(), 'Trash unexpectedly removed the exported file'
            assert message_texts(client, base, old_id)[-1] == ('assistant', old_answer)
            normal = get(client, base, '/api/search', q='uniquepersistedoldtoken', mode='keyword')
            including_trash = get(client, base, '/api/search', q='uniquepersistedoldtoken', mode='keyword', include_trash=1)
            assert not any(hit['cid'] == old_id for hit in normal['results']), 'Trash still appears in normal search'
            assert any(hit['cid'] == old_id for hit in including_trash['results']), 'Trashed chat missing from inclusive search'
            print('PASS trash: flag set, source retained, standard search excludes chat')

            post(client, base, '/api/organize', {'id': old_id, 'trashed': False})
            restored = get(client, base, '/api/state')
            assert chat(restored, old_id)['trashed'] == 0, 'Restored chat still marked as trashed'
            assert message_texts(client, base, old_id) == [
                ('user', old_prompt), ('assistant', old_answer)
            ], 'Restored messages changed or disappeared'
            searchable = get(client, base, '/api/search', q='uniquepersistedoldtoken', mode='keyword')
            assert any(hit['cid'] == old_id for hit in searchable['results']), 'Restored chat missing from normal search'
            assert chat(restored, new_id) is not None, 'Restoration removed the newly scanned chat'
            print('PASS restore: chat visible again, messages unchanged, normal search restored')

            # Exercise the same queue endpoints used by the UI's Delete
            # confirmation, with one synthetic native JSONL session. Real
            # remote deletion methods are booby-trapped for the entire run.
            local_id = 'smoke-native-local-delete'
            local_prompt = 'Synthetic local deletion should only touch a fake session.'
            local_answer = 'The recovery copy is verified before local removal.'
            local_file = sessions / 'rollout-synthetic.jsonl'
            original_bytes = synthetic_native_session(local_id, 'Synthetic Codex local session', local_prompt, local_answer)
            local_file.write_bytes(original_bytes)
            assert local_file.resolve().is_relative_to(fake_home.resolve())
            post(client, base, '/api/scan', {'path': str(sessions), 'up': 0})
            discovered = wait_for_scan(client, base, local_id)
            local_chat = chat(discovered, local_id)
            assert local_chat['kind'] == 'codex' and Path(local_chat['path']).resolve() == local_file.resolve(), local_chat
            assert message_texts(client, base, local_id) == [('user', local_prompt), ('assistant', local_answer)]

            with patch.object(server.deletions, 'enqueue', side_effect=AssertionError('Remote enqueue forbidden')), \
                 patch.object(server.deletions, 'action', side_effect=AssertionError('Remote action forbidden')):
                staged = post_result(client, base, '/api/delete-queue/add', {'ids': [local_id], 'mode': 'library'})
                pending = [item for item in staged['jobs'] if item['cid'] == local_id]
                assert len(pending) == 1, pending
                job = pending[0]
                assert job['local'] is True and job['mode'] == 'library' and job['state'] == 'queued', job
                result = post_result(client, base, '/api/delete-queue/action', {
                    'action': 'run', 'ids': [job['id']],
                })
                assert any(item['id'] == job['id'] for item in result['jobs'])
                finished, status = wait_for_local_delete(client, base, job['id'])

            assert finished['local'] and finished['state'] == 'confirmed', finished
            assert status['removed'] == [local_id], status['removed']
            recovery = Path(finished['recovery_path']).resolve()
            assert recovery.is_relative_to((home / 'temporary-index').resolve()), recovery
            assert recovery.read_bytes() == original_bytes, 'Recovery bytes changed'
            assert hashlib.sha256(recovery.read_bytes()).digest() == hashlib.sha256(original_bytes).digest()
            assert not local_file.exists(), 'Original synthetic source remained after confirmed local removal'
            assert local_id not in {entry['id'] for entry in archive.catalog()}
            assert local_id in archive.removed_ids(), 'Local tombstone missing'
            assert local_id in archive.settings().get('nativeCodexExcludedSessions', []), 'Native exclusion missing'
            remaining = get(client, base, '/api/state')
            assert chat(remaining, local_id) is None, 'Locally deleted chat still in viewer state'
            assert chat(remaining, old_id) and chat(remaining, new_id), 'Other synthetic chats changed'
            assert message_texts(client, base, old_id)[-1] == ('assistant', old_answer)
            assert message_texts(client, base, new_id)[-1] == ('assistant', new_answer)
            print('PASS local delete: /api/delete-queue/add + /api/delete-queue/action run => confirmed; '
                  'source removed, byte-identical private recovery, local tombstone, no remote action')
        finally:
            if server:
                server.shutdown()
                server.server_close()
            if archive:
                archive.close()
            native_homes_guard.stop()
    print('PASS isolation: synthetic exports and temporary index cleaned up')


if __name__ == '__main__':
    main()
