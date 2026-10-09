#!/usr/bin/env python3
r"""Synthetic HTTP regression: NATIVE Codex local deletion, never ChatGPT.

Run from the viewer source directory:
    runtime\python.exe -B docs\verify-local-index-removal-v1.1.28.py

Expected POST /api/local-codex/remove {"ids": [...]} schedules background
deletion of indexed native Codex JSONL sessions only. Deletion must verify a
private recovery copy before unlinking the ORIGINAL session file and tombstone
the viewer index. ChatGPT exporter .json/.md files must be refused untouched.
All source files, fake CODEX_HOME, SQLite databases, and HTTP sockets are
synthetic, temp-only. This test does not read a real user archive or account.
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import native_codex
import native_deletion
from viewer import Archive, Server


def codex_session(cid: str, token: str) -> bytes:
    records = [
        {'type': 'session_meta', 'payload': {
            'id': cid, 'originator': 'codex_cli',
            'title': 'New chat', 'timestamp': '2026-10-09T00:00:00Z'}},
        {'type': 'response_item', 'payload': {
            'role': 'user', 'content': [{'type': 'input_text', 'text': 'Prompt ' + token}]}},
        {'type': 'response_item', 'payload': {
            'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Answer ' + token}]}},
    ]
    return ''.join(json.dumps(item, sort_keys=True) + '\n' for item in records).encode('utf-8')


def chatgpt_export(cid: str, token: str) -> dict:
    mapping = {}
    for n, (role, text) in enumerate((('user', 'Prompt ' + token),
                                      ('assistant', 'Answer ' + token))):
        node = f'node-{n}'
        mapping[node] = {
            'id': node, 'parent': f'node-{n - 1}' if n else None,
            'children': [f'node-{n + 1}'] if n == 0 else [],
            'message': {'author': {'role': role},
                        'content': {'content_type': 'text', 'parts': [text]}}}
    return {'id': cid, 'title': 'Saved ChatGPT export', 'mapping': mapping,
            'current_node': 'node-1'}


def http_get(opener, base, endpoint, **query):
    url = base + endpoint
    if query:
        url += '?' + urllib.parse.urlencode(query)
    with opener.open(url, timeout=6) as response:
        assert response.status == 200, (endpoint, response.status)
        return json.load(response)


def http_post(opener, base, endpoint, body):
    req = urllib.request.Request(
        base + endpoint, data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    with opener.open(req, timeout=6) as response:
        result = json.load(response)
        assert response.status == 200 and isinstance(result, dict) and not result.get('error'), result
        return result


def must_reject(opener, base, ids, expected_reason=None):
    try:
        result = http_post(opener, base, '/api/local-codex/remove', {'ids': ids})
        raise AssertionError(f'Forbidden selection accepted: {ids!r} => {result!r}')
    except urllib.error.HTTPError as error:
        assert error.code == 400, (ids, error.code)
        if expected_reason:
            payload = json.loads(error.read() or b'{}')
            reason = str(payload.get('error', '')).lower()
            assert any(word in reason for word in expected_reason), (ids, payload)


def indexed_rows(archive, cid):
    tables = {'chats': 'id', 'messages': 'cid', 'chunks': 'cid', 'titles': 'cid',
              'chunk_rows': 'cid', 'title_rows': 'cid', 'vectors': 'cid',
              'organization': 'cid', 'manifest_entries': 'cid'}
    with archive.connect() as db:
        return {name: db.execute(f'SELECT COUNT(*) FROM {name} WHERE {column}=?',
                                 (cid,)).fetchone()[0] for name, column in tables.items()}


def read_messages(client, base, cid, token):
    value = http_get(client, base, '/api/messages', id=cid, limit=20)
    assert value['total'] == 2, (cid, value)
    assert [(m['role'], m['text']) for m in value['messages']] == [
        ('user', 'Prompt ' + token), ('assistant', 'Answer ' + token)], (cid, value)


def progress_job(status, cid):
    for row in status.get('index_jobs', []):
        if row.get('cid') == cid:
            return row
    for row in status.get('jobs', []):
        if row.get('cid') == cid and row.get('local') is True:
            return row
    return None


def wait_done(client, base, archive, removed, timeout=20):
    deadline = time.monotonic() + timeout
    seen = {}
    while time.monotonic() < deadline:
        status = http_get(client, base, '/api/delete-queue')
        seen = {cid: progress_job(status, cid) for cid in removed}
        failed = {cid: row for cid, row in seen.items()
                  if row and row.get('state') == 'failed'}
        assert not failed, f'Native local deletion failed: {failed}'
        if all(row and row.get('state') == 'confirmed' for row in seen.values()):
            assert removed <= archive.removed_ids(), ('Missing index tombstone', archive.removed_ids())
            return status
        time.sleep(.075)
    raise AssertionError(f'Native local deletion did not complete: {seen}')


def verify_recovery(db_root, originals):
    """Only inspect recovery artifacts under this synthetic viewer DB."""
    recovery_root = (db_root / 'native-codex-recovery').resolve()
    assert recovery_root.is_dir(), 'Verified private native recovery directory missing'
    copies = [p for p in recovery_root.rglob('session.jsonl') if p.is_file() and not p.is_symlink()]
    matched = {}
    for copy in copies:
        assert copy.resolve().is_relative_to(recovery_root)
        cid = str(native_codex.session_header(copy).get('id'))
        if cid in originals:
            assert copy.read_bytes() == originals[cid], (cid, copy)
            assert hashlib.sha256(copy.read_bytes()).digest() == hashlib.sha256(originals[cid]).digest()
            matched[cid] = copy
    assert set(matched) == set(originals), ('Missing verified native recoveries', matched)
    return matched


def main():
    with tempfile.TemporaryDirectory(prefix='viewer-native-local-smoke-') as directory:
        root = Path(directory)
        codex_home = root / 'synthetic-codex-home'
        sessions = codex_home / 'sessions'
        sessions.mkdir(parents=True)
        exports = root / 'synthetic-chatgpt-exports'
        exports.mkdir()
        db_root = root / 'synthetic-viewer-index'

        first, second, keep = 'native-new-chat-01', 'native-new-chat-02', 'native-keep-03'
        json_id, md_id = 'chatgpt-json-01', 'chatgpt-md-02'
        to_delete = {first, second}
        token = {first: 'nativetokenalpha', second: 'nativetokenbeta',
                 keep: 'nativetokengamma', json_id: 'exportjsontoken',
                 md_id: 'exportmarkdownword'}
        native_files = {
            first: sessions / 'rollout-synthetic-01.jsonl',
            second: sessions / 'rollout-synthetic-02.jsonl',
            keep: sessions / 'rollout-synthetic-03.jsonl',
        }
        originals = {cid: codex_session(cid, token[cid]) for cid in native_files}
        for cid, path in native_files.items():
            path.write_bytes(originals[cid])
            assert path.resolve().is_relative_to(sessions.resolve())

        json_file = exports / 'chatgpt-conversation.json'
        md_file = exports / 'chatgpt-conversation.md'
        json_file.write_text(json.dumps(chatgpt_export(json_id, token[json_id])), encoding='utf-8')
        md_file.write_text(
            '# Saved ChatGPT export\n'
            f'Conversation: https://chatgpt.com/c/{md_id}\n'
            f'## User\nPrompt {token[md_id]}\n'
            f'## Assistant\nAnswer {token[md_id]}\n', encoding='utf-8')
        export_files = {json_id: json_file, md_id: md_file}
        export_sha = {cid: hashlib.sha256(path.read_bytes()).digest()
                      for cid, path in export_files.items()}

        # Fails closed: all native source discovery and process guards use
        # synthetic state; never enumerate/inspect a user's real Codex home.
        with patch.object(native_codex, 'homes', return_value=[codex_home]), \
             patch.object(native_deletion, 'codex_process_running', return_value=False):
            archive = Archive(db_root, background_process=False)
            server = None
            try:
                archive.scan(exports, 0)
                assert not archive.status['errors'], archive.status['errors']
                archive.scan(sessions, 0)
                assert not archive.status['errors'], archive.status['errors']
                all_ids = {*native_files, *export_files}
                assert {r['id'] for r in archive.catalog()} == all_ids
                for cid in all_ids:
                    assert indexed_rows(archive, cid)['chats'] == 1
                    assert indexed_rows(archive, cid)['messages'] == 2
                assert all(next(r for r in archive.catalog() if r['id'] == cid)['kind'] == 'codex'
                           for cid in native_files)
                archive.enable_ui_cache()
                archive.cache_thread.join(timeout=8)
                assert archive.ui_cache and not archive.ui_cache['loading']
                server = Server(('127.0.0.1', 0), archive)
                # Synthetic process state only: do not inspect the OS process list.
                codex_running = threading.Event()
                codex_running.set()
                server.native.deletion_queue.process_running = codex_running.is_set
                server.native.deletion_queue.poll_interval = .1
                threading.Thread(target=server.serve_forever, daemon=True).start()
                base = f'http://127.0.0.1:{server.server_port}'
                client = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

                try:
                    http_post(urllib.request.build_opener(), base, '/api/local-codex/remove',
                              {'ids': [first]})
                    raise AssertionError('Unauthenticated native local removal accepted')
                except urllib.error.HTTPError as error:
                    assert error.code == 403, error.code
                with client.open(base + '/?token=' + server.token, timeout=6) as response:
                    response.read()
                for cid in all_ids:
                    read_messages(client, base, cid, token[cid])
                print('PASS fixtures/auth: native JSONL x3, ChatGPT JSON+MD x2, authenticated API')

                # A local-only native delete cannot accept ChatGPT export IDs.
                # A mixed native/export batch must reject as a whole, never
                # partially delete the otherwise-valid native session.
                with patch.object(server.deletions, 'enqueue', side_effect=AssertionError(
                         'ChatGPT remote enqueue attempted during rejected request')), \
                     patch.object(server.deletions, 'action', side_effect=AssertionError(
                         'ChatGPT remote action attempted during rejected request')):
                    for ids in ([json_id], [md_id], [first, json_id], [second, md_id]):
                        must_reject(client, base, ids, ('native', 'codex', 'jsonl', 'chatgpt'))
                    for ids in ([], [first, first], [first, 'missing-native-id']):
                        must_reject(client, base, ids)
                assert all(indexed_rows(archive, cid)['chats'] == 1 for cid in all_ids)
                for cid, path in export_files.items():
                    assert path.is_file()
                    assert hashlib.sha256(path.read_bytes()).digest() == export_sha[cid]
                print('PASS scope: ChatGPT exporter JSON/MD and mixed batches rejected, untouched')

                # Guard against accidentally routing any local request through
                # ChatGPT's browser or remote delete queue.
                held = threading.Event()
                release = threading.Event()
                original_tombstone = archive.remove_local_chat

                def guarded_tombstone(cid):
                    held.set()
                    if not release.wait(8):
                        raise AssertionError('Synthetic tombstone gate timed out')
                    return original_tombstone(cid)

                with patch.object(server.deletions, 'enqueue', side_effect=AssertionError(
                        'No ChatGPT remote enqueue is allowed')), \
                     patch.object(server.deletions, 'action', side_effect=AssertionError(
                        'No ChatGPT remote delete action is allowed')), \
                     patch.object(archive, 'remove_local_chat', side_effect=guarded_tombstone):
                    try:
                        start = time.monotonic()
                        accepted = http_post(client, base, '/api/local-codex/remove',
                                             {'ids': [first, second]})
                        assert time.monotonic() - start < 3, 'HTTP request waited for background deletion'
                        assert accepted.get('async') is True and accepted.get('native_codex') is True, accepted
                        assert set(accepted.get('accepted', ())) == to_delete, accepted
                        deadline = time.monotonic() + 4
                        while time.monotonic() < deadline:
                            queue = http_get(client, base, '/api/delete-queue')
                            if any((progress_job(queue, cid) or {}).get('state') == 'waiting'
                                   for cid in to_delete):
                                break
                            time.sleep(.05)
                        else:
                            raise AssertionError('Native deletion did not defer while Codex was open')
                        assert all(native_files[cid].read_bytes() == originals[cid] for cid in to_delete)
                        assert all(cid not in archive.removed_ids() for cid in to_delete)
                        print('PASS process guard: deletion waits while synthetic Codex process is open')
                        codex_running.clear()
                        assert held.wait(4), 'Local deletion worker did not start'
                        assert all(cid not in archive.removed_ids() for cid in to_delete)
                    finally:
                        codex_running.clear()
                        release.set()
                    wait_done(client, base, archive, to_delete)
                print('PASS async/no remote: HTTP acknowledged before background tombstone; jobs confirmed')

                for cid in to_delete:
                    assert not native_files[cid].exists(), f'Original native JSONL still exists: {cid}'
                    assert cid in archive.removed_ids()
                    assert all(count == 0 for count in indexed_rows(archive, cid).values())
                    assert cid not in {c['id'] for c in archive.catalog()}
                    assert not http_get(client, base, '/api/search', q=token[cid],
                                        mode='keyword', include_trash=1)['results']
                recovered = verify_recovery(db_root, {cid: originals[cid] for cid in to_delete})
                assert len(recovered) == 2
                print('PASS source/recovery: original JSONL files absent; verified byte-identical private recovery')

                assert native_files[keep].read_bytes() == originals[keep]
                for cid, path in export_files.items():
                    assert path.is_file()
                    assert hashlib.sha256(path.read_bytes()).digest() == export_sha[cid]
                for cid in (keep, json_id, md_id):
                    assert cid not in archive.removed_ids()
                    read_messages(client, base, cid, token[cid])
                print('PASS neighbors: unrelated native session and ChatGPT JSON/MD exports intact')

                # Original files are absent, but both the standard scan and
                # native session discovery must keep deleted IDs excluded.
                archive.scan(sessions, 0)
                archive.scan(exports, 0)
                server.native.discover()
                assert not archive.status['errors'], archive.status['errors']
                assert {r['id'] for r in archive.catalog()} == {keep, json_id, md_id}
                assert to_delete <= archive.removed_ids()
                for cid in (keep, json_id, md_id):
                    read_messages(client, base, cid, token[cid])
                print('PASS tombstones/rescan: native rediscovery cannot resurrect deleted IDs')

                # Deletion is not a re-entrant or remote operation.
                with patch.object(server.deletions, 'enqueue', side_effect=AssertionError(
                        'Remote enqueue forbidden')), patch.object(server.deletions, 'action',
                        side_effect=AssertionError('Remote action forbidden')):
                    must_reject(client, base, [first])
                assert to_delete <= archive.removed_ids()
                print('PASS repeat request: no remote action or native resurrection')
            finally:
                if server:
                    server.shutdown()
                    server.server_close()
                archive.close()
    print('PASS isolation: synthetic temporary sources, native recovery and SQLite cleaned')


if __name__ == '__main__':
    main()
