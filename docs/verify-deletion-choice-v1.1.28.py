#!/usr/bin/env python3
r"""Synthetic deletion-choice and provenance regressions; NEVER deletes real chats.

Run from project root:
    runtime\python.exe -B docs\verify-deletion-choice-v1.1.28.py

This constructs synthetic ChatGPT exports, a manifest-linked export, two
JSON-primary and two Markdown-primary explicitly temporary conversations,
an orphan, and a native Codex session in TemporaryDirectory. Remote success is supplied
ONLY as a synthetic verified receipt; the test never contacts ChatGPT.
Frontend assertions inspect the actual shipped HTML/JS statically (no browser
DOM engine is installed). They do not execute the browser UI.
"""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import native_codex
from chat_types import source_header
from deletion_queue import SCHEMA, write
from viewer import Archive, Server


def synthetic_chat(cid, marker):
    nodes = {}
    for idx, (role, content) in enumerate((('user', 'Question ' + marker),
                                          ('assistant', 'Answer ' + marker))):
        key = f'node-{idx}'
        nodes[key] = {'id': key, 'parent': f'node-{idx-1}' if idx else None,
                      'children': [f'node-{idx+1}'] if idx == 0 else [],
                      'message': {'author': {'role': role},
                                  'content': {'content_type': 'text', 'parts': [content]}}}
    # The viewer's streaming JSON header reader inspects properties preceding
    # the large mapping. Real ChatGPT exports carry this Boolean in their
    # envelope; keep it before mapping in both temporary and normal fixtures.
    return {'is_temporary_chat': False, 'id': cid, 'title': 'New chat',
            'mapping': nodes, 'current_node': 'node-1'}


def temporary_chat(cid, marker):
    """Saved-source evidence outranks a scoped exporter and synthesized URL.

    Use the explicit top-level `is_temporary_chat: true` Boolean, not a title,
    generated https://chatgpt.com/c/<id> URL or a guessed account. The marker
    belongs to the source conversation JSON; manifest entries deliberately
    omit it to exercise source-vs-wrapper precedence.
    """
    return dict(synthetic_chat(cid, marker), is_temporary_chat=True)


def temporary_markdown(cid, marker):
    """Misleading ChatGPT URL; temporary truth resides in companion JSON."""
    return ('# Saved temporary chat\n'
            f'Conversation: https://chatgpt.com/c/{cid}\n'
            f'## User\nQuestion {marker}\n'
            f'## Assistant\nAnswer {marker}\n')


def synthetic_native(cid):
    lines = [
        {'type': 'session_meta', 'payload': {
            'id': cid, 'originator': 'codex_cli', 'timestamp': '2026-10-09T00:00:00Z'}},
        {'type': 'response_item', 'payload': {
            'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Native fixture'}]}}
    ]
    return (''.join(json.dumps(item)+'\n' for item in lines)).encode()


def request(client, base, endpoint, values):
    req = urllib.request.Request(base + endpoint, data=json.dumps(values).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with client.open(req, timeout=8) as response:
        assert response.status == 200, (endpoint, response.status)
        value = json.load(response)
        assert isinstance(value, dict) and 'error' not in value, value
        return value


def reject(client, base, endpoint, values):
    req = urllib.request.Request(base + endpoint, data=json.dumps(values).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with client.open(req, timeout=8) as response:
            raise AssertionError((endpoint, 'unexpected success', response.status,
                                  response.read()[:500]))
    except urllib.error.HTTPError as exc:
        assert exc.code == 400, (endpoint, values, exc.code)
        return json.loads(exc.read() or b'{}').get('error', '')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def queued_job(result, cid, mode):
    rows = [r for r in result.get('jobs', []) if r['cid'] == cid]
    assert len(rows) == 1, (cid, rows)
    assert rows[0]['mode'] == mode and rows[0]['state'] == 'queued', rows[0]
    return rows[0]


def synthetic_receipt(queue, cid, root, remote_state='deleted'):
    """Simulate already-verified REMOTE result; no request or account access."""
    assert remote_state in ('deleted', 'unavailable'), remote_state
    row = next(r for r in queue.rows() if r['cid'] == cid)
    queue.snapshot(row)  # Saved only to private synthetic temporary archive.
    run = 'synthetic_verified_run_01'
    with queue.archive.connect() as db:
        db.execute('UPDATE deletion_jobs SET state=?,run=? WHERE id=?',
                   ('waiting', run, row['id']))
    receipt = dict(schema=SCHEMA, id=row['id'], cid=cid, scope=row['scope'], run=run,
                   state='confirmed', verified=True, remote_state=remote_state,
                   updated=time.time())
    write(root / '.viewer-queue' / 'receipts' / (row['id'] + '.json'), receipt)
    queue.stop_event.set()  # Disable dispatch; tick may ONLY ingest fixture receipt.
    queue.tick()
    state = next(r for r in queue.rows() if r['cid'] == cid)
    expected = 'confirmed' if remote_state == 'deleted' else 'failed'
    assert state['state'] == expected, state
    return state


class DeletionChoiceParser(HTMLParser):
    """Collect actual radio options inside the deletion-choice dialog."""
    def __init__(self):
        super().__init__()
        self.in_choice = False
        self.depth = 0
        self.radios = {}
        self.named = set()
        self.labels = []
        self._label_depth = 0
        self._label_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'dialog' and attrs.get('id') == 'delete-choice':
            self.in_choice = True
            self.depth = 1
        elif self.in_choice:
            if attrs.get('id'):
                self.named.add(attrs['id'])
            if tag == 'dialog':
                self.depth += 1
            if tag == 'label':
                self._label_depth += 1
                if self._label_depth == 1:
                    self._label_text = []
            if tag == 'input' and attrs.get('name') == 'delete-retention':
                self.radios[attrs.get('value')] = attrs

    def handle_data(self, data):
        if self.in_choice and self._label_depth:
            self._label_text.append(data)

    def handle_endtag(self, tag):
        if not self.in_choice:
            return
        if tag == 'label' and self._label_depth:
            self._label_depth -= 1
            if not self._label_depth:
                self.labels.append(' '.join(''.join(self._label_text).split()))
        if tag == 'dialog':
            self.depth -= 1
            if self.depth == 0:
                self.in_choice = False


def frontend_contract():
    html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'web/collections.js').read_text(encoding='utf-8')
    parsed = DeletionChoiceParser()
    parsed.feed(html)
    assert {'library', 'preserve'} <= parsed.radios.keys(), parsed.radios
    assert any('preserve' in label.lower() and 'local' in label.lower()
               for label in parsed.labels), parsed.labels
    assert any('delete' in label.lower() and 'local' in label.lower()
               for label in parsed.labels), parsed.labels
    assert "'/api/delete-choice/inspect'" in js, 'No provenance inspection endpoint in frontend'
    assert "'/api/delete-choice/submit'" in js, 'No provenance-aware mode submission endpoint in frontend'
    assert all(key in parsed.named for key in ('delete-choice-title',
                                               'delete-choice-warning',
                                               'delete-choice-notes',
                                               'delete-choice-add')), parsed.named
    assert ('delete-retention' in js and "const mode=" in js and
            ("{ids,mode}" in js or "mode:mode" in js)), (
        'Selected mode not submitted to backend')
    print('PASS UI structure: two retention radios and separate native/remote requests')

    # Static contract for reactive copy: selection must affect what is said
    # BEFORE queueing, not merely the mode sent to the server. Also require
    # provenance-sensitive copy so orphan exports do not claim remote linkage.
    # No JS engine/DOM automation is installed; this is a source contract.
    lowered = js.lower()
    assert ('addEventListener' in js or '.onchange' in js), (
        'No dynamic listener available for mode-specific deletion explanation')
    assert ('choiceCopy' in js and 'refreshChoice' in js and
            "mode==='library'" in js and
            "[name=delete-retention]" in js and
            'delete-choice-warning' in js), (
        'Mode-specific explanation missing')
    assert all(key in lowered for key in
               ('native:', 'linked:', 'temporary:', 'orphan:', 'unknown:')), (
        'No orphan or unknown-account UI branch; provenance can be misrepresented')
    assert 'temporary:' in lowered and 'no chatgpt' in lowered, (
        'Temporary mode description must explicitly exclude ChatGPT requests')
    assert ('provenance' in lowered or 'account' in lowered), (
        'No evidence/provenance information used by frontend selection text')
    assert 'job.mode' in js and 'job.local' in js and 'job.state' in js, (
        'Queue status copy is not tied to mode, local/remote provenance, and state')
    print('PASS UI messaging source contract: mode, provenance, queue state distinguished')


def main():
    with tempfile.TemporaryDirectory(prefix='viewer-deletion-choice-synthetic-') as directory:
        base = Path(directory)
        linked = base / 'chatgpt-linked'
        orphan = base / 'chatgpt-orphan'
        codex_home = base / 'fake-codex-home'
        sessions = codex_home / 'sessions'
        for path in (linked, orphan, sessions):
            path.mkdir(parents=True)
        indexdir = base / 'viewer-temp-index'

        keep_cid, wipe_cid = 'linked-chat-preserve-01', 'linked-chat-library-02'
        unavailable_cid = 'linked-chat-unavailable-06'
        orphan_cid, native_cid = 'local-orphan-unknown-03', 'native-codex-fixture-04'
        native_preserve_cid = 'native-codex-preserve-07'
        orphan_preserve_cid = 'local-orphan-preserve-08'
        temporary_delete_cid = 'temporary-chat-delete-09'
        temporary_preserve_cid = 'temporary-chat-preserve-10'
        md_temporary_delete_cid = 'temporary-md-delete-11'
        md_temporary_preserve_cid = 'temporary-md-preserve-12'
        unknown_cid = 'unknown-provenance-05'
        keep_file, wipe_file = linked/'preserve.json', linked/'library.json'
        unavailable_file = linked/'unavailable.json'
        orphan_file, native_file = orphan/'orphan.json', sessions/'rollout-fixture.jsonl'
        orphan_preserve_file = orphan/'orphan-preserve.json'
        temporary_delete_file = linked/'temporary-delete.json'
        temporary_preserve_file = linked/'temporary-preserve.json'
        md_delete_file = linked/'temporary-md-delete.md'
        md_preserve_file = linked/'temporary-md-preserve.md'
        md_delete_companion = linked/'temporary-md-delete-companion.json'
        md_preserve_companion = linked/'temporary-md-preserve-companion.json'
        native_preserve_file = sessions/'rollout-preserve.jsonl'
        unknown_file = orphan/'unknown.json'
        for path, cid in ((keep_file, keep_cid), (wipe_file, wipe_cid),
                          (unavailable_file, unavailable_cid),
                          (orphan_file, orphan_cid), (orphan_preserve_file, orphan_preserve_cid),
                          (unknown_file, unknown_cid)):
            path.write_text(json.dumps(synthetic_chat(cid, cid)), encoding='utf-8')
        for path,cid in ((temporary_delete_file,temporary_delete_cid),
                         (temporary_preserve_file,temporary_preserve_cid),
                         (md_delete_companion,md_temporary_delete_cid),
                         (md_preserve_companion,md_temporary_preserve_cid)):
            path.write_text(json.dumps(temporary_chat(cid,cid)),encoding='utf-8')
            saved=json.loads(path.read_text(encoding='utf-8'))
            assert saved.get('is_temporary_chat') is True and 'url' not in saved, saved
            assert source_header(path).get('is_temporary_chat') is True, (
                'Temporary marker was not visible in source header',path)
        for path,cid in ((md_delete_file,md_temporary_delete_cid),
                         (md_preserve_file,md_temporary_preserve_cid)):
            path.write_text(temporary_markdown(cid,cid),encoding='utf-8')
            assert 'is_temporary_chat' not in path.read_text(encoding='utf-8'),path
            assert f'Conversation: https://chatgpt.com/c/{cid}' in path.read_text(
                encoding='utf-8'),path
        for path in (keep_file,wipe_file,unavailable_file):
            assert source_header(path).get('is_temporary_chat') is False, (
                'Normal exporter fixture must explicitly disprove temporary mode',path)
        native_file.write_bytes(synthetic_native(native_cid))
        native_preserve_file.write_bytes(synthetic_native(native_preserve_cid))
        scope = 'proven-source-synthetic-scope'
        (linked/'conversation-index.json').write_text(json.dumps({
            'schema': 'chatgpt-library-index/v1',
            'scope': {'key': scope},
            'entries': [{'id': keep_cid, 'json': keep_file.name, 'title': 'Linked preserve'},
                        {'id': wipe_cid, 'json': wipe_file.name, 'title': 'Linked library'},
                        {'id': unavailable_cid, 'json': unavailable_file.name,
                         'title': 'Linked unavailable'},
                        # Deliberately manifest-scoped with NO temporary marker:
                        # source JSON must override apparent ChatGPT linkage.
                        {'id': temporary_delete_cid, 'json': temporary_delete_file.name,
                         'title': 'Temporary deletion'},
                        {'id': temporary_preserve_cid, 'json': temporary_preserve_file.name,
                         'title': 'Temporary preserve'},
                        # Temporary truth is ONLY in same-CID JSON; Markdown
                        # primary has a misleading online ChatGPT /c/ URL.
                        {'id': md_temporary_delete_cid, 'json': md_delete_companion.name,
                         'markdown': md_delete_file.name, 'title': 'MD-primary temporary delete'},
                        {'id': md_temporary_preserve_cid, 'json': md_preserve_companion.name,
                         'markdown': md_preserve_file.name,
                         'title': 'MD-primary temporary preserve'}],
        }), encoding='utf-8')
        # A second exporter handoff also references the delete companion from
        # the *preserve* conversation. Its JSON header belongs to the delete
        # CID, so it MUST NOT be treated as the preserve conversation's marker,
        # nor physically erased as part of deleting only its primary Markdown.
        # The canonical conversation-index contains the correct companion for
        # preserve, keeping this a realistic ambiguous/shared reference.
        (linked/'viewer-handoff.json').write_text(json.dumps({
            'schema':'chatgpt-library-index/v1',
            'entries':[{'id':md_temporary_preserve_cid,
                        'json':md_delete_companion.name,
                        'markdown':md_preserve_file.name,
                        'title':'Shared companion reference'}],
        }), encoding='utf-8')
        before = {p:sha(p) for p in (keep_file, wipe_file, unavailable_file, orphan_file,
                                    orphan_preserve_file, unknown_file, native_file,
                                    native_preserve_file, temporary_delete_file,
                                    temporary_preserve_file, md_delete_file,
                                    md_preserve_file, md_delete_companion,
                                    md_preserve_companion)}

        with patch.object(native_codex, 'homes', return_value=[codex_home]):
            archive = Archive(indexdir, background_process=False)
            server = None
            try:
                for root in (linked, orphan, sessions):
                    archive.scan(root, 0)
                    assert not archive.status['errors'], archive.status['errors']
                # Verify the saved companion references. Markdown-primary is
                # forced later, immediately before inspection, because the
                # preceding tests rescan this folder and prefer JSON.
                with archive.connect() as db:
                    for cid,md in ((md_temporary_delete_cid,md_delete_file),
                                   (md_temporary_preserve_cid,md_preserve_file)):
                        entry=db.execute(
                            'SELECT metadata FROM manifest_entries WHERE cid=? AND manifest=?',
                            (cid,str(linked/'conversation-index.json'))).fetchone()
                        assert entry,('MD companion manifest missing',cid)
                        meta=json.loads(entry['metadata'])
                        expected_json=(md_delete_companion if cid==md_temporary_delete_cid
                                       else md_preserve_companion)
                        assert meta['json']==expected_json.name,(cid,meta)
                        assert meta['markdown']==md.name
                    shadow=db.execute(
                        'SELECT metadata FROM manifest_entries WHERE cid=? AND '
                        'manifest=?',
                        (md_temporary_preserve_cid,str(linked/'viewer-handoff.json'))
                    ).fetchone()
                    assert shadow,'Synthetic shared companion reference missing'
                    assert json.loads(shadow['metadata'])['json']==md_delete_companion.name
                assert {c['id'] for c in archive.catalog()} == {
                    keep_cid, wipe_cid, unavailable_cid, orphan_cid, native_cid,
                    native_preserve_cid, orphan_preserve_cid, unknown_cid,
                    temporary_delete_cid, temporary_preserve_cid,
                    md_temporary_delete_cid, md_temporary_preserve_cid}
                archive.enable_ui_cache()
                archive.cache_thread.join(timeout=8)
                server = Server(('127.0.0.1', 0), archive)
                server.native.deletion_queue.process_running = lambda: True
                threading.Thread(target=server.serve_forever, daemon=True).start()
                url = f'http://127.0.0.1:{server.server_port}'
                client = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                with client.open(url+'/?token='+server.token, timeout=6) as response:
                    response.read()

                # Temporary is a source attribute, not account association.
                # These rows have genuine *synthetic* exporter manifest scope,
                # and the legacy importer synthesizes a ChatGPT URL from CID.
                # Neither is evidence that a temporary chat exists remotely.
                assert server.deletions.chat_account(temporary_delete_cid) == (
                    linked.resolve(),scope), 'Fixture must exercise scoped-manifest collision'
                temp_catalog = {c['id']:c for c in archive.catalog()}
                for cid in (temporary_delete_cid,temporary_preserve_cid):
                    assert temp_catalog[cid]['path'] in (
                        str(temporary_delete_file),str(temporary_preserve_file))
                    assert temp_catalog[cid]['url'] == 'https://chatgpt.com/c/'+cid, (
                        'Fixture no longer exercises the importer-synthesized ChatGPT URL',
                        temp_catalog[cid])
                    assert json.loads(Path(temp_catalog[cid]['path']).read_text(
                        encoding='utf-8'))['is_temporary_chat'] is True
                temp_choices=request(client,url,'/api/delete-choice/inspect',
                                     {'ids':[temporary_delete_cid,temporary_preserve_cid]})
                assert {row['id']:row['kind'] for row in temp_choices['choices']}=={
                    temporary_delete_cid:'temporary', temporary_preserve_cid:'temporary'
                }, ('Explicit temporary flag was overridden by linked scope/URL',temp_choices)
                assert all(cid not in archive.removed_ids() for cid in (
                    temporary_delete_cid,temporary_preserve_cid))
                print('PASS temporary provenance: explicit source marker wins over scoped manifest and synthesized URL')

                # Both retention choices for a temporary chat stay strictly
                # local. Refuse any ChatGPT request, even when a scoped exporter
                # manifest looks as if it can supply an account.
                with patch.object(server.deletions,'enqueue',side_effect=AssertionError(
                     'Temporary chat must not enqueue ChatGPT remote deletion')), \
                     patch.object(server.deletions,'action',side_effect=AssertionError(
                     'Temporary chat must not run ChatGPT remote deletion')), \
                     patch.object(server.deletions.browser,'check',side_effect=AssertionError(
                     'Temporary chat must not initiate remote account verification')):
                    for cid,mode,path in (
                        (temporary_delete_cid,'delete',temporary_delete_file),
                        (temporary_preserve_cid,'preserve',temporary_preserve_file),
                    ):
                        response=request(client,url,'/api/delete-choice/submit',
                                         {'ids':[cid],'mode':mode})
                        assert set(response.get('accepted',()))=={cid} and response.get('async') is True, response
                        deadline=time.monotonic()+12
                        while time.monotonic()<deadline:
                            jobs=[j for j in server.local_choice.rows() if j['cid']==cid]
                            if jobs and jobs[-1]['state'] in ('confirmed','failed'):break
                            time.sleep(.075)
                        else:raise AssertionError(f'Temporary {mode} did not finish')
                        assert jobs[-1]['state']=='confirmed',jobs
                        assert cid in archive.removed_ids(),(cid,mode)
                        assert all(row['id']!=cid for row in archive.catalog())
                        with archive.connect() as db:
                            assert not db.execute('SELECT 1 FROM chats WHERE id=?',(cid,)).fetchone()
                            assert not db.execute('SELECT 1 FROM messages WHERE cid=?',(cid,)).fetchone()
                        assert not any(j['cid']==cid for j in server.deletions.rows()),(
                            'Temporary chat acquired a ChatGPT remote job',cid)
                        if mode=='delete':
                            assert not path.exists(),f'Temporary delete left exclusive source: {path}'
                            matches=[r for r in (indexdir/'local-choice-recovery').glob('*.json')
                                     if r.is_file() and sha(r)==before[path]]
                            assert matches,f'Temporary delete lacked SHA-identical private recovery: {cid}'
                        else:
                            assert path.is_file() and sha(path)==before[path],(
                                'Temporary preserve changed original source',path)
                    # Rescan the same manifest and still-present temporary
                    # preserve source; neither removed conversation may return.
                    archive.scan(linked,0)
                    assert not archive.status['errors'],archive.status['errors']
                    for cid in (temporary_delete_cid,temporary_preserve_cid):
                        assert cid in archive.removed_ids()
                        assert all(row['id']!=cid for row in archive.catalog())
                        assert not any(j['cid']==cid for j in server.deletions.rows())
                print('PASS temporary modes: delete removes exclusive source after recovery, '
                      'preserve keeps original, both tombstoned/no rediscovery/no remote calls')

                # Second temporary path: user saved Markdown as the INDEXED
                # primary transcript, while its authorized same-CID JSON
                # companion carries the actual ChatGPT temporary marker.
                # The MD's plausible /c/ URL and export account scope are
                # misleading; neither may authorize a remote deletion.
                # The preceding JSON-primary test rescanned the same folder,
                # which normally reselects JSON. Recreate the user's MD-
                # primary indexed condition immediately before inspection.
                with archive.connect() as db:
                    for cid,md in ((md_temporary_delete_cid,md_delete_file),
                                   (md_temporary_preserve_cid,md_preserve_file)):
                        stat=md.stat()
                        changed=db.execute(
                            'UPDATE chats SET path=?,fingerprint=? WHERE id=?',
                            (str(md),f'{stat.st_mtime_ns}:{stat.st_size}',cid))
                        assert changed.rowcount==1,(cid,md)
                md_ids=(md_temporary_delete_cid,md_temporary_preserve_cid)
                md_rows={c['id']:c for c in archive.catalog()}
                for cid,md,companion in (
                    (md_temporary_delete_cid,md_delete_file,md_delete_companion),
                    (md_temporary_preserve_cid,md_preserve_file,md_preserve_companion),
                ):
                    assert md_rows[cid]['path']==str(md),(
                        'Test failed to force Markdown as saved primary',cid,md_rows[cid])
                    assert md_rows[cid]['url']=='https://chatgpt.com/c/'+cid
                    assert source_header(md)=={},'Markdown must carry no JSON header flag'
                    header=source_header(companion)
                    assert (header.get('id')==cid and
                            header.get('is_temporary_chat') is True),header
                    assert sha(md)==before[md] and sha(companion)==before[companion]
                    assert server.deletions.chat_account(cid)==(linked.resolve(),scope)
                md_choices=request(client,url,'/api/delete-choice/inspect',{'ids':list(md_ids)})
                assert {row['id']:row['kind'] for row in md_choices['choices']}=={
                    md_temporary_delete_cid:'temporary',
                    md_temporary_preserve_cid:'temporary'
                },('Scoped MD + misleading URL defeated same-CID JSON evidence',md_choices)
                print('PASS Markdown-primary provenance: scoped online-looking .md '
                      'overridden by same-CID temporary JSON companion')

                # The deletion task may remove an exclusive Markdown source,
                # but never the referenced companion JSON (which may be
                # shared with another manifest entry). Preserve retains both.
                with patch.object(server.deletions,'enqueue',side_effect=AssertionError(
                     'MD-primary temporary must not enqueue ChatGPT deletion')), \
                     patch.object(server.deletions,'action',side_effect=AssertionError(
                     'MD-primary temporary must not execute ChatGPT deletion')), \
                     patch.object(server.deletions.browser,'check',side_effect=AssertionError(
                     'MD-primary temporary must not check ChatGPT account')):
                    for cid,mode,md,companion in (
                        (md_temporary_delete_cid,'delete',md_delete_file,md_delete_companion),
                        (md_temporary_preserve_cid,'preserve',md_preserve_file,md_preserve_companion),
                    ):
                        result=request(client,url,'/api/delete-choice/submit',
                                       {'ids':[cid],'mode':mode})
                        assert result.get('mode')==mode and set(result.get('accepted',[]))=={cid},result
                        assert result.get('async') is True,result
                        deadline=time.monotonic()+12
                        while time.monotonic()<deadline:
                            jobs=[j for j in server.local_choice.rows() if j['cid']==cid]
                            if jobs and jobs[-1]['state'] in ('confirmed','failed'):break
                            time.sleep(.075)
                        else:raise AssertionError(f'MD-primary temporary {mode} did not finish')
                        assert jobs[-1]['state']=='confirmed',jobs
                        assert cid in archive.removed_ids()
                        assert all(row['id']!=cid for row in archive.catalog())
                        with archive.connect() as db:
                            assert not db.execute('SELECT 1 FROM chats WHERE id=?',(cid,)).fetchone()
                            assert not db.execute('SELECT 1 FROM messages WHERE cid=?',(cid,)).fetchone()
                        assert not any(row['cid']==cid for row in server.deletions.rows())
                        assert companion.is_file() and sha(companion)==before[companion],(
                            'Temporary MD cleanup altered JSON companion',companion)
                        if mode=='delete':
                            assert not md.exists(),('Exclusive MD source was not deleted',md)
                            matches=[f for f in (indexdir/'local-choice-recovery').glob('*.md')
                                     if f.is_file() and sha(f)==before[md]]
                            assert matches,('No verified original MD recovery',cid)
                        else:
                            assert md.is_file() and sha(md)==before[md],(
                                'Preserve mode changed original primary Markdown',md)
                    archive.scan(linked,0)
                    assert not archive.status['errors'],archive.status['errors']
                    for cid in md_ids:
                        assert cid in archive.removed_ids()
                        assert all(row['id']!=cid for row in archive.catalog())
                        assert not any(row['cid']==cid for row in server.deletions.rows())
                    assert md_delete_companion.is_file()
                    assert sha(md_delete_companion)==before[md_delete_companion]
                    assert md_preserve_companion.is_file()
                    assert sha(md_preserve_companion)==before[md_preserve_companion]
                    assert md_preserve_file.is_file() and sha(md_preserve_file)==before[md_preserve_file]
                print('PASS Markdown-primary temporary actions: no remote; exclusive .md '
                      'removed with private recovery or preserved; JSON companions '
                      'unchanged and neither conversation rediscovered')

                # Native local removal is NEVER a ChatGPT remote queue action.
                with patch.object(server.deletions, 'enqueue', side_effect=AssertionError(
                     'ChatGPT remote enqueue called for native Codex')), \
                     patch.object(server.deletions, 'action', side_effect=AssertionError(
                     'ChatGPT remote action called for native Codex')):
                    status = request(client, url, '/api/local-codex/remove', {'ids': [native_cid]})
                    assert status.get('native_codex') is True and status.get('async') is True
                    assert status.get('accepted') == [native_cid]
                    native_queue = next(j for j in server.native.deletion_queue.rows()
                                        if j['session_id'] == native_cid)
                    assert native_queue['mode'] == 'library'
                    assert sha(native_file) == before[native_file]
                    server.native.deletion_queue.action('pause', [native_queue['id']])
                print('PASS native: local-only mode, remote never invoked, original kept while waiting')

                # Known-account exporter has explicit manifest provenance. Its
                # two choices BOTH request ChatGPT remote deletion; preserve
                # keeps original source bytes and library deletes the original
                # only after a verified deleted receipt.
                linked_account = server.deletions.chat_account(keep_cid)
                assert linked_account == (linked.resolve(), scope), linked_account
                inspect = request(client, url, '/api/delete-choice/inspect',
                                  {'ids': [keep_cid, wipe_cid]})
                assert {r['id']:r['kind'] for r in inspect['choices']} == {
                    keep_cid:'linked', wipe_cid:'linked'}, inspect
                preserved = request(client, url, '/api/delete-choice/submit',
                                    {'ids': [keep_cid], 'mode': 'preserve'})
                preserve_job = queued_job(preserved, keep_cid, 'preserve')
                assert preserve_job['scope'] == scope and preserve_job['root'] == str(linked.resolve())
                assert sha(keep_file) == before[keep_file]
                assert keep_cid not in archive.removed_ids(), (
                    'Linked preserve tombstoned before confirmed remote deletion')
                assert any(row['id']==keep_cid for row in archive.catalog()), (
                    'Linked preserve removed viewer entry before confirmed remote deletion')
                print('PASS linked preserve queued: mode=preserve remote job, original/index kept pending proof')

                # Native Codex and orphan preserve are different: keep original
                # source, remove index, and never enqueue any remote deletion.
                with patch.object(server.deletions, 'enqueue', side_effect=AssertionError(
                     'Local-only preserve must never queue ChatGPT remote deletion')), \
                     patch.object(server.deletions, 'action', side_effect=AssertionError(
                     'Local-only preserve must never run ChatGPT remote deletion')):
                    for cid,path in ((native_preserve_cid,native_preserve_file),
                                     (orphan_preserve_cid,orphan_preserve_file)):
                        held = request(client,url,'/api/delete-choice/submit',
                                       {'ids':[cid], 'mode':'preserve'})
                        assert set(held.get('accepted',[]))=={cid} and held.get('async') is True, held
                        deadline=time.monotonic()+12
                        while time.monotonic()<deadline and cid not in archive.removed_ids():
                            time.sleep(.08)
                        assert cid in archive.removed_ids(), f'Local preserve was not tombstoned: {cid}'
                        assert sha(path)==before[path], f'Local preserve changed original source: {path}'
                        assert not any(job['cid']==cid for job in server.deletions.rows())
                print('PASS native/orphan preserve: original files kept; index removed without remote jobs')

                library_result = request(client, url, '/api/delete-choice/submit',
                                         {'ids': [wipe_cid], 'mode': 'delete'})
                library = queued_job(library_result, wipe_cid, 'library')
                assert library['scope'] == scope and library['root'] == str(linked.resolve())
                assert sha(wipe_file) == before[wipe_file]
                unavailable_result = request(client, url, '/api/delete-choice/submit',
                                             {'ids': [unavailable_cid], 'mode': 'delete'})
                unavailable_job = queued_job(unavailable_result, unavailable_cid, 'library')
                assert unavailable_job['scope'] == scope
                assert sha(unavailable_file) == before[unavailable_file]
                print('PASS linked: manifest scope proven; deletion mode only queued, no source removed')

                # No real remote requests: freeze dispatcher and feed verified
                # synthetic receipt as the sole event permitting cleanup.
                with patch.object(server.deletions.browser, 'connected_scopes',
                                  return_value={'unrelated-connected-account'}):
                    orphan_class = request(client, url, '/api/delete-choice/inspect',
                                           {'ids': [orphan_cid]})
                    unknown_class = request(client, url, '/api/delete-choice/inspect',
                                            {'ids': [unknown_cid]})
                assert orphan_class['choices'][0]['kind'] == 'orphan', orphan_class
                assert unknown_class['choices'][0]['kind'] == 'unknown', unknown_class
                with patch.object(server.deletions, 'enqueue', side_effect=AssertionError(
                     'Unknown-owner delete must not enqueue remote request')):
                    message = reject(client, url, '/api/delete-choice/submit',
                                     {'ids':[unknown_cid], 'mode':'delete'})
                    assert any(word in message.lower() for word in ('unknown','account','owner')), message
                assert unknown_file.exists() and sha(unknown_file)==before[unknown_file]
                assert not any(r['cid']==unknown_cid for r in server.deletions.rows())
                assert sha(orphan_file) == before[orphan_file]
                print('PASS orphan/unknown: unrelated signed-in account never becomes chat provenance')

                with patch.object(server.deletions, 'enqueue', side_effect=AssertionError(
                     'Orphan local-only action must NOT queue remote deletion')), \
                     patch.object(server.deletions, 'action', side_effect=AssertionError(
                     'Orphan local-only action must NOT run remote deletion')), \
                     patch.object(server.deletions.browser, 'connected_scopes',
                                  return_value={'unrelated-connected-account'}):
                    orphan_local = request(client, url, '/api/delete-choice/submit',
                                           {'ids': [orphan_cid], 'mode': 'delete'})
                    assert set(orphan_local.get('accepted', [])) == {orphan_cid}, orphan_local
                    assert orphan_local.get('async') is True, orphan_local
                    deadline = time.monotonic()+12
                    while time.monotonic()<deadline:
                        if orphan_cid in archive.removed_ids() and not orphan_file.exists():
                            break
                        time.sleep(.08)
                    else:
                        raise AssertionError('Exclusive orphan source deletion not complete')
                    assert not any(r['cid'] == orphan_cid for r in server.deletions.rows())
                print('PASS orphan local delete: exclusive source removed without invented account')

                # Stop any background dispatch BEFORE mocking a verified remote
                # response; receipt still exercises the actual cleanup path.
                server.deletions.stop_event.set()
                assert keep_cid not in archive.removed_ids()
                assert sha(keep_file)==before[keep_file]
                preserve_confirmed=synthetic_receipt(server.deletions,keep_cid,linked)
                assert preserve_confirmed['mode']=='preserve' and preserve_confirmed['state']=='confirmed'
                assert keep_file.is_file() and sha(keep_file)==before[keep_file]
                assert keep_cid in archive.removed_ids(), (
                    'Linked preserve did not tombstone after remote deletion confirmation')
                assert all(c['id']!=keep_cid for c in archive.catalog())
                with archive.connect() as db:
                    assert not db.execute('SELECT 1 FROM chats WHERE id=?',(keep_cid,)).fetchone()
                    assert not db.execute('SELECT 1 FROM messages WHERE cid=?',(keep_cid,)).fetchone()
                archive.scan(linked,0)
                assert keep_file.is_file() and sha(keep_file)==before[keep_file]
                assert keep_cid in archive.removed_ids()
                assert all(c['id']!=keep_cid for c in archive.catalog())
                print('PASS linked preserve receipt: remote deleted proof tombstones index; original saved file retained')
                assert wipe_file.is_file(), 'Local cleanup occurred without verified receipt'
                synthetic_receipt(server.deletions, wipe_cid, linked)
                assert not wipe_file.exists(), 'Library-mode source was not cleaned after proof'
                assert wipe_cid in archive.removed_ids()
                assert keep_file.is_file() and not orphan_file.exists()
                assert unknown_file.is_file() and sha(unknown_file)==before[unknown_file]
                print('PASS library: remote verified first, then exclusive source cleaned locally')

                # A provider's "unavailable" is NOT a verified deletion.
                # Even a syntactically verified confirmation receipt with
                # remote_state=unavailable must fail the library cleanup and
                # leave the original local file AND indexed chat untouched.
                assert unavailable_cid not in archive.removed_ids()
                unavailable = synthetic_receipt(
                    server.deletions, unavailable_cid, linked, remote_state='unavailable')
                assert unavailable['state'] == 'failed', unavailable
                assert 'did not confirm deletion' in unavailable['error'].lower(), unavailable
                assert unavailable_file.is_file()
                assert sha(unavailable_file) == before[unavailable_file]
                assert unavailable_cid not in archive.removed_ids()
                assert any(c['id'] == unavailable_cid for c in archive.catalog())
                assert archive.page(unavailable_cid)['total'] == 2
                # A subsequent queue tick must not reinterpret the old
                # unavailable receipt as proof permitting physical removal.
                server.deletions.tick()
                assert unavailable_file.is_file() and sha(unavailable_file) == before[unavailable_file]
                assert unavailable_cid not in archive.removed_ids()
                assert next(r for r in server.deletions.rows()
                            if r['cid'] == unavailable_cid)['state'] == 'failed'
                print('PASS unavailable: verified receipt does not authorize library cleanup; '
                      'job failed, original/index preserved across retry tick')
            finally:
                if server:
                    server.shutdown()
                    server.server_close()
                archive.close()

    print('PASS isolation: all synthetic sources, index, and receipts deleted with temp fixture')
    frontend_contract()


if __name__ == '__main__':
    main()
