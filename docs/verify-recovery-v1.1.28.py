#!/usr/bin/env python3
r"""Isolated fault-injection probes for Offline Chat Viewer 1.1.28.

Run from the viewer root:
    runtime\python.exe -B docs\verify-recovery-v1.1.28.py

All generated data and Windows installer copies live in TemporaryDirectory.
Imports touch the installed Python source, never the real .viewer-data or accounts.
The corrected backend behaviors are asserted alongside unrelated recovery probes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from archive_backup import BackupManager, build_zip, extract_zip, plan_files
from backup_snapshot import Snapshot, SnapshotPending
from browser_companion import BrowserCompanion
from drive_backup import Drive
import drive_backup
from library_files import FileCatalog
from native_codex import session_header
from native_connection import NativeConnection
from source_reader import native_conversation
from viewer import Archive


def emit(name, **details):
    print(name + " " + json.dumps(details, sort_keys=True))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive_fixture(base):
    return Archive(base / "db", background_process=False)


def sqlite_faults(base):
    data = base / "sqlite"
    data.mkdir()
    archive = archive_fixture(data)
    source = data / "chat.md"
    source.write_text("# Persist\n## User\nold body\n", encoding="utf8")
    archive.scan(data, 0)
    cid = next(c["id"] for c in archive.catalog())
    original = archive.page(cid)["messages"][0]["text"]
    original_fp = next(c for c in archive.catalog() if c["id"] == cid)["fingerprint"]
    # Inject a late INSERT failure after store() deleted the old title/messages.
    with archive.connect() as db:
        db.execute("CREATE TRIGGER inject_store_abort BEFORE INSERT ON messages "
                   "BEGIN SELECT RAISE(ABORT, 'injected-index-failure'); END")
    source.write_text("# Persist\n## User\nnew body to index\n", encoding="utf8")
    archive.scan(data, 0)
    assert archive.status["errors"]
    assert archive.page(cid)["messages"][0]["text"] == original
    assert next(c for c in archive.catalog() if c["id"] == cid)["fingerprint"] == original_fp
    with archive.connect() as db:
        assert db.execute("SELECT count(*) FROM chunks WHERE cid=?", (cid,)).fetchone()[0] > 0
        assert db.execute("SELECT count(*) FROM title_rows WHERE cid=?", (cid,)).fetchone()[0] == 1
        db.execute("DROP TRIGGER inject_store_abort")
    archive.scan(data, 0)
    assert not archive.status["errors"] and archive.page(cid)["messages"][0]["text"] == "new body to index"
    archive.close()
    emit("sqlite-index-abort", rollback_preserves_message_fts_fingerprint=True,
         retry_after_removing_fault=True)

    # Simulate an old-schema migration interrupted before its last kind repair.
    legacy = data / "legacy"
    legacy.mkdir()
    with sqlite3.connect(legacy / "archive.sqlite3") as db:
        db.execute("CREATE TABLE chats(id TEXT PRIMARY KEY,title TEXT,url TEXT,created REAL,"
                   "updated REAL,kind TEXT,project TEXT,path TEXT,fingerprint TEXT,"
                   "count INTEGER,folder TEXT)")
        db.execute("CREATE TABLE messages(cid TEXT,seq INTEGER,role TEXT,channel TEXT,"
                   "text TEXT,time REAL,visible INTEGER,PRIMARY KEY(cid,seq))")
        db.execute("CREATE TABLE organization(cid TEXT PRIMARY KEY,category TEXT DEFAULT '',"
                   "pinned INTEGER DEFAULT 0,position REAL DEFAULT 0,alias TEXT DEFAULT '')")
        db.execute("INSERT INTO chats VALUES ('legacy','L','',0,0,'work','', '', '',1,'')")
        db.execute("INSERT INTO messages VALUES('legacy',0,'user','','preserved',0,1)")
        db.execute("CREATE TRIGGER inject_migration_abort BEFORE UPDATE ON chats "
                   "BEGIN SELECT RAISE(ABORT, 'injected-migration-failure'); END")
    db.close()
    try:
        Archive(legacy, background_process=False)
        raise AssertionError("Expected migration exception")
    except sqlite3.DatabaseError as error:
        assert "injected-migration-failure" in str(error)
    with sqlite3.connect(legacy / "archive.sqlite3") as db:
        db.execute("DROP TRIGGER inject_migration_abort")
    db.close()
    reopened = Archive(legacy, background_process=False)
    assert reopened.page("legacy")["messages"][0]["text"] == "preserved"
    with reopened.connect() as db:
        columns = {r["name"] for r in db.execute("PRAGMA table_info(messages)")}
        assert "extras" in columns
    reopened.close()
    emit("sqlite-migration-abort", failed_then_reopened=True, legacy_message_preserved=True)


def backup_faults(base):
    root = base / "exports"
    root.mkdir()
    original = root / "original.md"
    original.write_text("# Original\n## User\n![image](assets/image.png)\n", encoding="utf8")
    asset = root / "assets" / "image.png"
    asset.parent.mkdir()
    asset.write_bytes(b"original-image")
    snap = Snapshot(base / "snap", root, "job-1", lambda **kw: None, lambda: None)
    files, fp, missing = plan_files(root, documents=[original], snapshot=snap)
    assert "assets/image.png" in files and not missing
    destination = base / "Chat-Archive-Full.zip"
    manifest = {"schema": "offline-chat-viewer/backup-v1", "mode": "full",
                "files": files}
    build_zip(snap.tree, destination, files, manifest)
    old_zip_hash = sha(destination.read_bytes())

    # A stale staged file with identical size+mtime passes Snapshot's quick
    # staged-key reuse, but ZIP packaging checks its saved content digest.
    staged = snap.tree / "assets" / "image.png"
    st = staged.stat()
    staged.write_bytes(b"x" * st.st_size)
    os.utime(staged, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert snap.capture(asset)[0].read_bytes() != asset.read_bytes()
    try:
        build_zip(snap.tree, destination, files, manifest)
        raise AssertionError("Corrupt captured bytes should not package")
    except ValueError as error:
        assert "failed captured-byte" not in str(error)
        assert "changed during packaging" in str(error)
    assert sha(destination.read_bytes()) == old_zip_hash
    snap.invalidate("assets/image.png")
    files, _, missing = plan_files(root, documents=[original], snapshot=snap)
    build_zip(snap.tree, destination, files, {**manifest, "files": files})
    assert sha(destination.read_bytes()) == old_zip_hash  # deterministic replacement
    emit("backup-staged-corruption", corrupt_capture_reused_until_hash_check=True,
         completed_zip_preserved=True, invalidation_recovers=True)

    # A missing source is retryable and original verified ZIP stays in place.
    asset.unlink()
    snap2 = Snapshot(base / "snap2", root, "job-2", lambda **kw: None, lambda: None)
    try:
        snap2.capture(asset)
        raise AssertionError("Missing file accepted")
    except SnapshotPending:
        pass
    assert sha(destination.read_bytes()) == old_zip_hash
    asset.write_bytes(b"original-image")
    assert snap2.capture(asset)[0].read_bytes() == asset.read_bytes()
    emit("backup-exporter-missing", snapshot_pending=True, existing_zip_preserved=True,
         new_capture_after_restoration=True)

    # Missing reference is recorded in manifest inventory, not silently fabricated.
    asset.unlink()
    missing_snapshot = Snapshot(base / "missing-snap", root, "job-3",
                                lambda **kw: None, lambda: None)
    no_asset, _, missing = plan_files(root, documents=[original], snapshot=missing_snapshot)
    assert "assets/image.png" not in no_asset and missing
    emit("backup-missing-reference", file_excluded=True,
         manifest_warning=missing[0]["reason"])

    # Force a partial ZIP write and ensure a preexisting completed ZIP survives.
    asset.write_bytes(b"original-image")
    interrupted = Snapshot(base / "snap4", root, "job-4", lambda **kw: None, lambda: None)
    current, _, _ = plan_files(root, documents=[original], snapshot=interrupted)
    # This later fixture's regenerated asset has a new mtime, so it produces a
    # different deterministic manifest/ZIP from the initial baseline.
    build_zip(interrupted.tree, destination, current, {**manifest, "files": current})
    current_zip_hash = sha(destination.read_bytes())
    count = [0]
    def interrupted_check():
        count[0] += 1
        if count[0] >= 3:
            raise InterruptedError("injected pack interruption")
    try:
        build_zip(interrupted.tree, destination, current, {**manifest, "files": current},
                  check=interrupted_check)
        raise AssertionError("Interrupted ZIP build unexpectedly completed")
    except InterruptedError:
        pass
    assert sha(destination.read_bytes()) == current_zip_hash
    partial = destination.with_suffix(".zip.partial")
    assert partial.exists()
    build_zip(interrupted.tree, destination, current, {**manifest, "files": current})
    assert sha(destination.read_bytes()) == current_zip_hash
    emit("backup-package-interruption", stable_slot_kept=True, partial_remains=True,
         next_packaging_recovers=True)

    # Inject extract failure after writing an entry, then inspect incomplete residue.
    extract_calls = [0]
    def stop_extract():
        extract_calls[0] += 1
        if extract_calls[0] == 3:
            raise InterruptedError("injected ZIP extraction interruption")
    failed_import = base / "incomplete-import"
    try:
        extract_zip(destination, failed_import, check=stop_extract)
        raise AssertionError("Import should be interrupted")
    except InterruptedError:
        pass
    assert failed_import.exists()
    clean_import = extract_zip(destination, base / "recovered-import")
    assert (clean_import / "archive" / "assets" / "image.png").read_bytes() == b"original-image"
    emit("backup-import-interruption", incomplete_import_directory_retained=True,
         fresh_import_restores=True)


def import_index_fault(base):
    zip_path = base / "two-conversations.zip"
    sources = {"first.md": "# First\n## User\nfirst saved message\n",
               "second.md": "# Second\n## User\nsecond saved message\n"}
    manifest = {"schema": "offline-chat-viewer/backup-v1", "mode": "full",
                "files": {name: {"size": len(body.encode()), "sha256": sha(body.encode()),
                                 "mtime_ns": 0} for name, body in sources.items()},
                "conversations": [{"path": name, "id": "fixture-" + name.split(".")[0],
                                   "title": name.split(".")[0].title(),
                                   "created": 1000, "updated": 1000,
                                   "kind": "chat"} for name in sources]}
    with zipfile.ZipFile(zip_path, "w") as z:
        for name, body in sources.items():
            z.writestr("archive/" + name, body)
        z.writestr("backup-manifest.json", json.dumps(manifest))
    archive = archive_fixture(base / "viewer")
    manager = BackupManager(archive, ROOT)
    original_store = archive.store
    attempts = [0]
    def fail_second_store(*args, **kwargs):
        attempts[0] += 1
        if attempts[0] == 2:
            raise RuntimeError("injected second conversation failure")
        return original_store(*args, **kwargs)
    archive.store = fail_second_store
    try:
        manager.import_zip(zip_path)
        manager.worker.join(timeout=12)
        assert not manager.worker.is_alive()
        indexed = archive.catalog()
        assert len(indexed) == 1, indexed
        assert manager.status()["progress"]["phase"] == "Import needs attention"
        assert len(list((archive.data_dir / "imports").iterdir())) == 1
        archive.store = original_store
        manager.import_zip(zip_path)
        manager.worker.join(timeout=12)
        assert not manager.worker.is_alive()
        assert len(archive.catalog()) == 2
        assert manager.status()["progress"]["phase"] == "Import complete"
        emit("backup-import-index-interruption", first_chat_committed_before_second_failure=True,
             first_import_directory_retained=True, retry_indexes_remaining_chat=True,
             separate_import_directories=len(list((archive.data_dir / "imports").iterdir())))
    finally:
        archive.store = original_store
        manager.close()
        archive.close()


def attachment_faults(base):
    root = base / "file-root"
    catalog_dir = root / "attachments"
    catalog_dir.mkdir(parents=True)
    path = catalog_dir / "sample.bin"
    expected = b"intact-image-12"
    actual = b"CORRUPT-BYTES!!"
    assert len(expected) == len(actual)
    path.write_bytes(actual)
    (catalog_dir / "library-index.json").write_text(json.dumps({
        "schema": "chatgpt-library-index/v1",
        "entries": [{"id": "file-fixture", "name": "sample.bin",
                     "path": "attachments/sample.bin",
                     "size": len(expected), "sha256": sha(expected),
                     "status": "saved", "conversation_ids": ["fixture-chat"]}]
    }), encoding="utf8")
    archive = archive_fixture(base / "attachment-archive")
    try:
        archive.save_settings({"scan_start": str(root)})
        files = FileCatalog(archive)
        listed = files.list()["entries"]
        assert len(listed) == 1
        assert sha(actual) != sha(expected)
        try:
            files.file(listed[0]["key"])
            raise AssertionError("Mismatched file was served")
        except FileNotFoundError:
            pass
        assert not files.list()["entries"][0]["available"]
        emit("attachment-same-size-corruption", blocked_on_open=True,
             identified_corrupt_after_verification=True)
        path.unlink()
        assert not files.list()["entries"][0]["available"]
        try:
            files.file(listed[0]["key"])
            raise AssertionError("Missing file was served")
        except FileNotFoundError:
            pass
        path.write_bytes(expected)
        assert files.file(listed[0]["key"])[0].read_bytes() == expected
        assert files.list()["entries"][0]["available"]
        # Previously verified bytes cannot remain trusted after a file changes.
        previous = path.stat()
        path.write_bytes(actual)
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        try:
            files.file(listed[0]["key"])
            raise AssertionError("A changed previously-verified file was served")
        except FileNotFoundError:
            pass
        path.write_bytes(expected)
        assert files.file(listed[0]["key"])[0].read_bytes() == expected
        emit("attachment-missing-recovery", missing_blocked=True, restored_access=True)
    finally:
        archive.close()


def companion_and_native_faults(base):
    data = base / "companion-db"
    a = archive_fixture(data)
    class Queue:
        archive = a
        def chat_account(self, cid):
            return base, "scope-fixture"
    try:
        companion = BrowserCompanion(Queue())
        first = companion.check("fixture-conversation")
        with a.connect() as db:
            db.execute("UPDATE browser_checks SET done=1 WHERE id=?", (first["id"],))
        second = companion.check("fixture-conversation")
        with a.connect() as db:
            unfinished = db.execute("SELECT COUNT(*) FROM browser_checks WHERE done=0").fetchone()[0]
        assert second["id"] != first["id"] and unfinished == 1
        third = companion.check("fixture-conversation")
        assert third["id"] == second["id"]
        emit("companion-completed-check", id_reused=first["id"] == second["id"],
             new_pending_requests=unfinished)
    finally:
        a.close()

    # NativeConnection reads this state on startup if enabled is present.
    native_dir = base / "native-state"
    native_dir.mkdir()
    class Browser:
        archive = type("ArchiveStub", (), {"data_dir": native_dir})()
        def statuses(self):
            return []
    (native_dir / "native-connection-state.json").write_text("{MALFORMED", encoding="utf8")
    (native_dir / "native-connection-enabled.json").write_text('{"enabled":true}', encoding="utf8")
    damaged = NativeConnection(Browser())
    assert damaged.status()["phase"] == "error" and not damaged.alive()
    assert "unreadable" in damaged.status()["error"]
    assert (native_dir / "native-connection-state.json").read_text(encoding="utf8") == "{MALFORMED"
    emit("native-connection-corrupt-state", constructor_raises=False,
         original_corruption_retained_for_diagnosis=True)
    (native_dir / "native-connection-state.json").write_text('{"phase":"blocked"}', encoding="utf8")
    connected = NativeConnection(Browser())
    assert connected.status()["phase"] == "blocked" and not connected.alive()
    emit("native-connection-state-repaired", startup_succeeds=True, helper_not_spawned=True)

    native_session = base / "session.jsonl"
    head = {"type": "session_meta", "payload": {"id": "fixture-native",
                                                "originator": "codex_cli", "timestamp": "2026-10-09"}}
    response = {"type": "response_item", "payload": {"role": "assistant", "content": [
        {"type": "output_text", "text": "saved native message"}]}}
    native_session.write_text(json.dumps(head) + "\n" + json.dumps(response) +
                              "\n{\"type\":\"response_item\",", encoding="utf8")
    assert session_header(native_session)["id"] == "fixture-native"
    parsed = native_conversation(native_session.read_text(encoding="utf8"), native_session)
    assert len(parsed["messages"]) == 1
    native_session.write_text(json.dumps(head) + "\n{BROKEN}\n" +
                              json.dumps(response) + "\n", encoding="utf8")
    try:
        native_conversation(native_session.read_text(encoding="utf8"), native_session)
        raise AssertionError("Malformed interior native record accepted")
    except json.JSONDecodeError:
        emit("native-jsonl-truncation", trailing_partial_ignored=True,
             malformed_interior_rejected=True)


def oauth_fault(base):
    drive = Drive(base / "oauth")
    drive.configure({"installed": {"client_id": "fixture.apps.googleusercontent.com",
                                    "client_secret": "fixture"}})
    original_open = drive_backup.webbrowser.open
    urls = []
    drive_backup.webbrowser.open = lambda url: urls.append(url) or True
    entered = threading.Event()
    release = threading.Event()
    def fake_token(_):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("fixture callback timeout")
        return {"access_token": "fake", "refresh_token": "fake-refresh", "expires_in": 3600}
    drive._token = fake_token
    drive.request = lambda *args, **kw: {"user": {"emailAddress": "fixture@example.test"}}
    callback_thread = None
    try:
        drive.connect()
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(urls[0]).query)
        url = params["redirect_uri"][0] + "?" + urllib.parse.urlencode(
            {"state": params["state"][0], "code": "fixture-code"})
        result = []
        def callback():
            with urllib.request.urlopen(url, timeout=8) as response:
                result.append(response.read())
        callback_thread = threading.Thread(target=callback, daemon=True)
        callback_thread.start()
        assert entered.wait(3), "OAuth exchange did not start"
        first_listener = drive.listener
        drive.disconnect()
        assert not drive.status()["connected"]
        assert drive.listener is None
        drive.connect()
        second_listener = drive.listener
        assert first_listener is not second_listener
        release.set()
        callback_thread.join(timeout=5)
        assert result
        assert not drive.status()["connected"]
        assert drive.status()["phase"] == "waiting"
        assert drive.listener is second_listener
        emit("oauth-disconnect-callback", credentials_restored_after_disconnect=
             drive.status()["connected"], restored_phase=drive.status()["phase"])
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(urls[1]).query)
        followup = params["redirect_uri"][0] + "?" + urllib.parse.urlencode(
            {"state": params["state"][0], "code": "new-attempt"})
        with urllib.request.urlopen(followup, timeout=5) as response:
            assert b"is connected" in response.read()
        assert drive.status()["connected"] and drive.status()["phase"] == "connected"
        drive.disconnect()
        assert not drive.status()["connected"] and drive.status()["phase"] == "disconnected"
        emit("oauth-listener-ownership", expired_callback_left_new_listener_intact=True,
             new_callback_can_connect=True, final_disconnect_honored=True)
    finally:
        release.set()
        drive_backup.webbrowser.open = original_open
        if drive.listener is not None:
            drive.listener.shutdown()
        if callback_thread:
            callback_thread.join(timeout=3)


def updater_fault(base):
    if os.name != "nt":
        emit("updater-windows", skipped="requires Windows PowerShell")
        return
    root = base / "update-copy"
    root.mkdir()
    data = root / ".viewer-data"
    data.mkdir()
    shutil.copy2(ROOT / "apply-update.ps1", root / "apply-update.ps1")
    current = root / "one.txt"
    current.write_bytes(b"before")
    version = "9.9.9"
    payload = data / "updates" / ("v" + version) / "payload"
    payload.mkdir(parents=True)
    changed = payload / "one.txt"
    changed.write_bytes(b"after!")
    # A second file's checksum disagrees: validation must abort before copying one.txt.
    other = payload / "two.txt"
    other.write_bytes(b"second")
    files = [{"path": "one.txt", "sha256": sha(changed.read_bytes())},
             {"path": "two.txt", "sha256": "0" * 64}]
    marker = data / "pending-update.json"
    def write_marker():
        marker.write_text(json.dumps({"version": version,
                                      "payload": str(payload), "files": files}), encoding="utf8")
    def apply():
        run = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                              "-ExecutionPolicy", "Bypass", "-File",
                              str(root / "apply-update.ps1")],
                             capture_output=True, text=True, timeout=20)
        assert (data / "update-result.json").exists(), (run.stdout, run.stderr)
        return json.loads((data / "update-result.json").read_text(encoding="utf-8-sig"))
    write_marker()
    bad = apply()
    assert bad["installed"] is False and current.read_bytes() == b"before" and marker.exists()
    emit("updater-bad-later-hash", early_file_unchanged=True, pending_retained=True)
    files[-1]["sha256"] = sha(other.read_bytes())
    write_marker()
    good = apply()
    assert good["installed"] and current.read_bytes() == b"after!" and not marker.exists()
    emit("updater-retry-after-hash-fix", installed=True, rollback_copy_recorded=
         Path(good["rollback"], "one.txt").read_bytes() == b"before")

    # Simulate sudden PowerShell process death immediately after the first
    # live file copy. Instrument ONLY the isolated copy of the shipped script.
    sudden = base / "abrupt-update-copy"
    sudden.mkdir()
    local_data = sudden / ".viewer-data"
    local_data.mkdir()
    untouched = (ROOT / "apply-update.ps1").read_text(encoding="utf8")
    needle = "        Copy-Item -LiteralPath $row.Source -Destination $row.Target -Force"
    assert untouched.count(needle) == 1
    modified = untouched.replace(
        needle,
        needle + "\n        if ($row.Relative -eq 'first.txt') { [Environment]::Exit(91) }")
    local_script = sudden / "apply-update.ps1"
    local_script.write_text(modified, encoding="utf8")
    staged = local_data / "updates" / "v9.9.9" / "payload"
    staged.mkdir(parents=True)
    prior = {"first.txt": b"v1-first", "second.txt": b"v1-second"}
    next_version = {"first.txt": b"v2-first", "second.txt": b"v2-second"}
    for name, value in prior.items():
        (sudden / name).write_bytes(value)
    for name, value in next_version.items():
        (staged / name).write_bytes(value)
    pending = local_data / "pending-update.json"
    pending.write_text(json.dumps({
        "version": "9.9.9", "payload": str(staged),
        "files": [{"path": key, "sha256": sha(value)}
                  for key, value in next_version.items()]}), encoding="utf8")
    command = ["powershell.exe", "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-File", str(local_script)]
    interrupted = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert interrupted.returncode == 91, interrupted.stderr
    assert (sudden / "first.txt").read_bytes() == next_version["first.txt"]
    assert (sudden / "second.txt").read_bytes() == prior["second.txt"]
    assert pending.exists() and not (local_data / "update-result.json").exists()
    journal = local_data / "update-transaction.json"
    assert journal.exists()
    data = json.loads(journal.read_text(encoding="utf-8-sig"))
    assert len(data["files"]) == 2
    assert all((Path(data["rollback"]) / name).read_bytes() == value
               for name, value in prior.items())
    local_script.write_text(untouched, encoding="utf8")
    # Even with a now-corrupt staged payload, the next invocation must restore
    # both preupdate files from the durable journal before checking new hashes.
    (staged / "second.txt").write_bytes(b"BAD-STAGE")
    failed_retry = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert failed_retry.returncode == 0, failed_retry.stderr
    assert all((sudden / name).read_bytes() == value for name, value in prior.items())
    assert pending.exists() and not journal.exists()
    assert json.loads((local_data / "update-result.json").read_text(
        encoding="utf-8-sig"))["installed"] is False
    emit("updater-abrupt-recovery-staged-bad", original_version_restored=True,
         update_deferred=True, marker_kept=True)
    (staged / "second.txt").write_bytes(next_version["second.txt"])
    recovered = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert recovered.returncode == 0, recovered.stderr
    assert not pending.exists()
    assert all((sudden / name).read_bytes() == value for name, value in next_version.items())
    emit("updater-abrupt-process-exit", partial_live_install_observed_at_crash=True,
         journal_restores_old_version=True, corrected_stage_installs=True)

    # Separate crash point: payload fully installed and pending marker removed,
    # but durable journal still present. Finalization must verify installed SHA
    # and retain the good new release, not roll it back unnecessarily.
    finished = base / "postcommit-exit-copy"
    finished.mkdir()
    finished_data = finished / ".viewer-data"
    finished_data.mkdir()
    finished_payload = finished_data / "updates" / "v9.9.9" / "payload"
    finished_payload.mkdir(parents=True)
    for name, original in prior.items():
        (finished / name).write_bytes(original)
        (finished_payload / name).write_bytes(next_version[name])
    finish_marker = finished_data / "pending-update.json"
    finish_marker.write_text(json.dumps({
        "version": "9.9.9", "payload": str(finished_payload),
        "files": [{"path": key, "sha256": sha(value)}
                  for key, value in next_version.items()]}), encoding="utf8")
    marker_line = "    Remove-Item -LiteralPath $pendingPath"
    assert untouched.count(marker_line) == 1
    finish_script = finished / "apply-update.ps1"
    finish_script.write_text(untouched.replace(
        marker_line, marker_line + "\n    [Environment]::Exit(92)"), encoding="utf8")
    finish_command = ["powershell.exe", "-NoProfile", "-NonInteractive",
                      "-ExecutionPolicy", "Bypass", "-File", str(finish_script)]
    crash = subprocess.run(finish_command, capture_output=True, text=True, timeout=20)
    assert crash.returncode == 92, crash.stderr
    assert not finish_marker.exists()
    assert (finished_data / "update-transaction.json").exists()
    finish_script.write_text(untouched, encoding="utf8")
    finalized = subprocess.run(finish_command, capture_output=True, text=True, timeout=20)
    assert finalized.returncode == 0, finalized.stderr
    assert all((finished / name).read_bytes() == value for name, value in next_version.items())
    assert not (finished_data / "update-transaction.json").exists()
    status = json.loads((finished_data / "update-result.json").read_text(encoding="utf-8-sig"))
    assert status["installed"] and status["recovered"] == "verified-complete"
    emit("updater-postcommit-exit", completed_install_retained=True,
         journal_verified_and_cleared=True)


def main():
    with tempfile.TemporaryDirectory(prefix="offline-viewer-recovery-v1.1.28-") as scratch:
        base = Path(scratch)
        for name, check in (
            ("sqlite-tests", sqlite_faults),
            ("backup-tests", backup_faults),
            ("import-tests", import_index_fault),
            ("attachment-tests", attachment_faults),
            ("integration-tests", companion_and_native_faults),
            ("oauth-tests", oauth_fault),
            ("updater-tests", updater_fault),
        ):
            directory = base / name
            directory.mkdir()
            check(directory)
    print("All disposable fixtures removed; no real archive or connection was opened.")


if __name__ == "__main__":
    main()
