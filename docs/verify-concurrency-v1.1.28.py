#!/usr/bin/env python3
r"""Concurrency and revision-boundary probes for Offline Chat Viewer 1.1.28.

Run: runtime\python.exe -B docs\verify-concurrency-v1.1.28.py
Creates its own export sources, SQLite archives and authenticated loopback server.
It does not open the installed .viewer-data, Google Drive or any live archive.
Output names describe observed bugs; the tests are expected to pass even while
those bugs remain, so they can also detect changed behavior after future fixes.
"""
import contextlib
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import viewer
from viewer import Archive, Server
from find_text import conversation_matches


def emit(name, **data):
    print(name + ": " + json.dumps(data, sort_keys=True))


def record(cid, messages):
    """Minimal real mapping export, selected leaf is final node."""
    mapping = {}
    for i, (role, text) in enumerate(messages):
        ident = "node-" + str(i)
        mapping[ident] = {
            "id": ident, "parent": "node-" + str(i - 1) if i else None,
            "children": ["node-" + str(i + 1)] if i + 1 < len(messages) else [],
            "message": {
                "author": {"role": role},
                "content": {"content_type": "text", "parts": [text]},
                "create_time": i + 1,
            }
        }
    return {"id": cid, "title": "Revision fixture", "mapping": mapping,
            "current_node": "node-" + str(len(messages) - 1)}


def emit_file(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    # File length changes in all transition probes; timestamp granularity does
    # not control whether the actual file change is recognized.


def authenticated_server(archive):
    server = Server(("127.0.0.1", 0), archive)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = "http://127.0.0.1:" + str(server.server_port)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(origin + "/?token=" + server.token, timeout=5) as response:
        response.read()
    return server, opener, origin


def get_json(opener, address):
    with opener.open(address, timeout=6) as response:
        return json.load(response)


def fragmented_message_revision_and_search():
    with tempfile.TemporaryDirectory(prefix="viewer-fragment-epoch-") as folder:
        home = Path(folder)
        src = home / "exports"
        src.mkdir()
        path = src / "epoch.json"
        old = "oldepoched " + "A" * 55000
        new = "newepoched " + "B" * 56000
        emit_file(path, record("epoch", [("user", "intro"), ("assistant", old)]))
        archive = Archive(home / "db", background_process=False)
        server = None
        try:
            archive.scan(src, 0)
            archive.enable_ui_cache()
            assert archive.cache_thread is not None
            archive.cache_thread.join(timeout=5)
            assert not archive.ui_cache["loading"]
            server, opener, origin = authenticated_server(archive)
            initial = get_json(opener, origin + "/api/messages?id=epoch&bytes=8192&limit=5")
            first = initial["messages"][-1]
            assert first["text_complete"] is False and first["text"].startswith("oldepoched")
            assert len(first["text_hash"]) == 64

            # Exporter atomically changes the source while a fragment request
            # is pending. No scan is required for the foreground reader to see
            # the new file; the archive FTS still contains the previous epoch.
            emit_file(path, record("epoch", [("user", "intro"), ("assistant", new)]))
            try:
                get_json(
                    opener, origin + "/api/message-text?id=epoch&seq="
                    + str(first["seq"]) + "&offset=" + str(first["text_next"])
                    + "&bytes=131072&hash=" + first["text_hash"])
                raise AssertionError("Cross-revision fragment was accepted")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
                error = json.load(exc)["error"]
                assert "changed" in error.lower(), error
            fresh = get_json(opener, origin + "/api/messages?id=epoch&bytes=8192&limit=5")
            assert fresh["messages"][-1]["text"].startswith("newepoched")

            # While the foreground page has the latest source, FTS is the
            # durable index until a rescan commits the new revision.
            indexed_old = archive.search("oldepoched", "keyword")["results"]
            indexed_new = archive.search("newepoched", "keyword")["results"]
            assert indexed_old and not indexed_new
            archive.scan(src, 0)
            archive.publish_sources([archive.live_sources["epoch"]])
            after = archive.search("newepoched", "keyword")["results"]
            assert after and not archive.search("oldepoched", "keyword")["results"]
            emit("fragment-epoch-guard", initial_epoch="old", fragment_epoch="new",
                 cross_revision_fragment_rejected=True, new_source_page=True,
                 fts_lags_until_scan=True, fts_recovers_after_scan=True)
        finally:
            if server:
                server.shutdown()
                server.server_close()
            archive.close()


def page_multi_select_snapshot():
    with tempfile.TemporaryDirectory(prefix="viewer-page-epoch-") as folder:
        home = Path(folder)
        src = home / "exports"
        src.mkdir()
        file = src / "epoch.json"
        emit_file(file, record("page-epoch", [("user", "original"), ("assistant", "old answer")]))
        archive = Archive(home / "db", background_process=False)
        try:
            archive.scan(src, 0)
            original_connect = archive.connect
            reached = threading.Event()
            committed = threading.Event()
            failed = []

            @contextlib.contextmanager
            def traced_connect():
                with original_connect() as conn:
                    if threading.current_thread() is threading.main_thread():
                        def hook(sql):
                            if sql.startswith("SELECT * FROM messages WHERE cid="):
                                reached.set()
                                if not committed.wait(5):
                                    raise TimeoutError("Rescan missed deterministic query seam")
                        conn.set_trace_callback(hook)
                    yield conn

            archive.connect = traced_connect

            def writer():
                if not reached.wait(5):
                    failed.append("Reader did not reach rows query")
                    committed.set()
                    return
                try:
                    emit_file(file, record("page-epoch", [
                        ("user", "new prompt"), ("assistant", "new answer"), ("assistant", "third")
                    ]))
                    archive.scan(src, 0)
                except BaseException as err:
                    failed.append(str(err))
                finally:
                    committed.set()

            thread = threading.Thread(target=writer, daemon=True)
            thread.start()
            try:
                page = archive.page("page-epoch", limit=100)
            finally:
                thread.join(timeout=8)
                archive.connect = original_connect
            assert not failed, failed
            assert page["total"] == 2 and len(page["messages"]) == 2, page
            emit("sqlite-page-snapshot-guard", reported_total=page["total"],
                 actual_rows=len(page["messages"]), mixed_snapshot=False)
        finally:
            archive.close()


def semantic_build_update_epoch():
    """Stub only optional heavyweight embedder; run real build orchestration and DB writes."""
    with tempfile.TemporaryDirectory(prefix="viewer-semantic-epoch-") as folder:
        home = Path(folder)
        src = home / "exports"
        src.mkdir()
        file = src / "epoch.json"
        emit_file(file, record("semantic-epoch", [("user", "entry"), ("assistant", "baseline vecword")]))
        archive = Archive(home / "db", background_process=False)
        try:
            archive.scan(src, 0)
            snapshot_taken = threading.Event()
            resume = threading.Event()
            failures = []

            def paused_embed(self, batch, np):
                snapshot_taken.set()
                if not resume.wait(6):
                    raise TimeoutError("Timed out before rescan")
                with self.lock, self.connect() as db:
                    for row, part in batch:
                        body = row["title"] + "\n" + row["text"]
                        db.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?,?,?)",
                                   (row["cid"], row["seq"], part,
                                    hashlib.sha256(body.encode()).hexdigest(), b"placeholder"))
                self.semantic_state["count"] += len(batch)

            archive._embed_batch = types.MethodType(paused_embed, archive)
            fake_torch = types.ModuleType("torch")
            fake_torch.set_num_threads = lambda count: None
            fake_st = types.ModuleType("sentence_transformers")
            fake_st.SentenceTransformer = lambda *args, **kwargs: object()
            fake_numpy = types.ModuleType("numpy")

            def build():
                try:
                    archive.build_semantic(allow_setup=False)
                except BaseException as err:
                    failures.append(str(err))

            with patch.dict(sys.modules, {
                "numpy": fake_numpy, "torch": fake_torch, "sentence_transformers": fake_st,
            }), patch.object(viewer, "activate_semantic", lambda: None):
                worker = threading.Thread(target=build, daemon=True)
                worker.start()
                assert snapshot_taken.wait(6), "Semantic worker never loaded the prior FTS"
                emit_file(file, record("semantic-epoch", [
                    ("user", "entry"), ("assistant", "updated newvecword")
                ]))
                archive.scan(src, 0)
                assert archive.semantic_state["ready"] is False
                resume.set()
                worker.join(timeout=6)
            assert not worker.is_alive() and not failures
            assert archive.semantic_state["ready"] is False, archive.semantic_state
            with archive.connect() as db:
                vector_row = db.execute(
                    "SELECT hash FROM vectors WHERE cid=? AND seq=1",
                    ("semantic-epoch",)).fetchone()
            assert vector_row is None
            emit("semantic-epoch-invalidation", ready=False, stale_vectors_removed=True,
                 new_content_searchable=bool(archive.search("newvecword", "keyword")["results"]),
                 model_used="stub-only")
        finally:
            archive.close()


def phrase_overlap_threshold():
    """Exercise both sides of a single FTS 200-character overlap."""
    with tempfile.TemporaryDirectory(prefix="viewer-phrase-threshold-") as folder:
        home = Path(folder)
        src = home / "sources"
        src.mkdir()
        archive = Archive(home / "db", background_process=False)
        outcomes = []
        try:
            for words, offset in [(25, 995), (26, 995), (26, 1003)]:
                phrase = " ".join("word%03d" % i for i in range(words))
                assert len(phrase) == 8 * words - 1
                body = "z" * (offset - 1) + " " + phrase + " END"
                cid = "phrase-" + str(words) + "-" + str(offset)
                path = src / (cid + ".md")
                path.write_text(body, encoding="utf-8")
                item = {
                    "id": cid, "title": cid, "url": "", "created": 0, "updated": 0,
                    "kind": "chat", "project": "", "messages": [
                        {"role": "user", "channel": "", "text": body,
                         "time": 0, "visible": 1, "extras": {}}
                    ],
                }
                stat = path.stat()
                archive.store(item, path, str(stat.st_mtime_ns) + ":" + str(stat.st_size), src, {})
                with archive.connect() as db:
                    chunks = [r["text"] for r in db.execute(
                        "SELECT text FROM chunks WHERE cid=?", (cid,))]
                exact = [r for r in archive.search(phrase, "exact")["results"]
                         if r["cid"] == cid and r["seq"] == 0]
                found = conversation_matches(archive, cid, phrase)["results"]
                assert len(found) == 1 and len(exact) == 1
                outcomes.append({
                    "length": len(phrase), "start": offset,
                    "fits_single_chunk": any(phrase in c for c in chunks),
                    "archive_exact_hits": len(exact), "in_chat_find_hits": len(found)
                })
            assert [r["archive_exact_hits"] for r in outcomes] == [1, 1, 1], outcomes
            emit("phrase-overlap-threshold", scenarios=outcomes)
        finally:
            archive.close()


def settings_http_commit_reorder():
    """Exercise actual concurrent /api/settings request handlers on a disposable server."""
    with tempfile.TemporaryDirectory(prefix="viewer-settings-order-") as folder:
        archive = Archive(Path(folder) / "db", background_process=False)
        server = None
        try:
            server, opener, origin = authenticated_server(archive)
            originally = archive.save_settings
            entered = threading.Event()
            release = threading.Event()
            responses, failures = [], []

            def slowed(values):
                if values.get("theme") == "light":
                    entered.set()
                    if not release.wait(6):
                        raise TimeoutError("First theme write blocked too long")
                return originally(values)

            archive.save_settings = slowed

            def request(theme):
                try:
                    body = json.dumps({"theme": theme}).encode()
                    req = urllib.request.Request(
                        origin + "/api/settings", data=body,
                        headers={"Content-Type": "application/json", "Origin": origin},
                        method="POST")
                    with opener.open(req, timeout=7) as response:
                        responses.append((theme, response.status, json.load(response)))
                except BaseException as exc:
                    failures.append((theme, str(exc)))

            earlier = threading.Thread(target=request, args=("light",), daemon=True)
            later = threading.Thread(target=request, args=("black",), daemon=True)
            earlier.start()
            assert entered.wait(5)
            later.start()
            # The second HTTP handler now waits behind the first write; it
            # cannot overtake the earlier arrival while the first is blocked.
            threading.Event().wait(.12)
            assert later.is_alive() and not responses, (responses, failures)
            release.set()
            earlier.join(timeout=5)
            later.join(timeout=5)
            assert not earlier.is_alive() and not later.is_alive() and not failures, failures
            assert archive.settings()["theme"] == "black"
            emit("settings-http-order", request_order=["light", "black"],
                 completion_order=[x[0] for x in responses],
                 persisted_theme=archive.settings()["theme"],
                 user_last_action_did_not_win=False)
        finally:
            if server:
                server.shutdown()
                server.server_close()
            archive.close()


def delayed_http_page_isolation():
    """A hung chat read must not block a separate conversation HTTP request."""
    with tempfile.TemporaryDirectory(prefix="viewer-http-interleave-") as folder:
        home = Path(folder)
        src = home / "exports"
        src.mkdir()
        emit_file(src / "slow.json", record("slow", [("user", "slow message")]))
        emit_file(src / "fast.json", record("fast", [("user", "fast message")]))
        archive = Archive(home / "db", background_process=False)
        server = None
        try:
            archive.scan(src, 0)
            original = archive.foreground_page
            entered = threading.Event()
            release = threading.Event()
            results, errors = {}, []

            def paused_page(cid, *args):
                if cid == "slow":
                    entered.set()
                    if not release.wait(6):
                        raise TimeoutError("Delayed request exceeded fixture deadline")
                return original(cid, *args)

            archive.foreground_page = paused_page
            server, opener, origin = authenticated_server(archive)

            def request(name):
                try:
                    results[name] = get_json(opener, origin + "/api/messages?id=" + name)
                except Exception as error:
                    errors.append(str(error))

            slow_thread = threading.Thread(target=request, args=("slow",), daemon=True)
            fast_thread = threading.Thread(target=request, args=("fast",), daemon=True)
            slow_thread.start()
            assert entered.wait(5)
            fast_thread.start()
            fast_thread.join(timeout=5)
            assert not fast_thread.is_alive()
            assert "fast" in results and "slow" not in results, (results, errors)
            assert results["fast"]["messages"][0]["text"] == "fast message"
            release.set()
            slow_thread.join(timeout=5)
            assert not slow_thread.is_alive() and not errors
            assert results["slow"]["messages"][0]["text"] == "slow message"
            emit("delayed-http-independent-chats",
                 fast_completed_before_slow=True, paths_are_independent=True)
        finally:
            if server:
                server.shutdown()
                server.server_close()
            archive.close()


if __name__ == "__main__":
    fragmented_message_revision_and_search()
    page_multi_select_snapshot()
    semantic_build_update_epoch()
    phrase_overlap_threshold()
    settings_http_commit_reorder()
    delayed_http_page_isolation()
    print("Concurrency probes complete; isolated databases and servers closed.")
