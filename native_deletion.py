"""Reversible local removal of validated Codex session JSONL files."""
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import native_codex
from native_codex import session_header


QUEUE_FILE = "native-deletion.sqlite3"
EXCLUSIONS_SETTING = "nativeCodexExcludedSessions"
FINAL_STATES = {"confirmed", "cancelled"}
ACTIVE_STATES = {"queued", "waiting", "running"}


class _Deferred(RuntimeError):
    pass


def codex_process_running():
    """Return whether a Codex process is present; fail closed on probe errors."""
    if os.name == "nt":
        command = ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/FO", "CSV", "/NH"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=6, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"Could not check running processes: {error}") from error
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "tasklist could not inspect running processes")
        try:
            names = [row[0].casefold() for row in csv.reader(result.stdout.splitlines()) if row]
        except csv.Error as error:
            raise RuntimeError(f"Could not read tasklist output: {error}") from error
    else:
        try:
            result = subprocess.run(
                ["ps", "-A", "-o", "comm="], capture_output=True, text=True, timeout=3, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"Could not check running processes: {error}") from error
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "ps could not inspect running processes")
        names = [Path(line.strip()).name.casefold() for line in result.stdout.splitlines() if line.strip()]
    return any(Path(name).name.startswith("codex") for name in names)


def _digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _stat_key(path):
    info = Path(path).stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class NativeDeletionQueue:
    """Durable, local-only queue. Codex-owned SQLite files are never opened here."""

    def __init__(self, archive, process_running=None, poll_interval=7.5, session_lock=None):
        self.archive = archive
        self.database = archive.data_dir / QUEUE_FILE
        self.recovery_root = archive.data_dir / "native-codex-recovery"
        self.process_running = process_running or codex_process_running
        self.poll_interval = max(0.1, float(poll_interval))
        self.session_lock = session_lock or threading.RLock()
        self.lock = threading.RLock()
        self.tick_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = None
        self.guard = {"checked": None, "codex_running": None, "error": ""}
        self._initialize()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _initialize(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database, timeout=5)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                """CREATE TABLE IF NOT EXISTS native_deletion_jobs(
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    source_path TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    recovery_path TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    state TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL,
                    updated REAL NOT NULL,
                    run TEXT NOT NULL DEFAULT ''
                )"""
            )
            if "title" not in {r[1] for r in db.execute("PRAGMA table_info(native_deletion_jobs)")}:
                db.execute("ALTER TABLE native_deletion_jobs ADD COLUMN title TEXT DEFAULT ''")
            db.commit()
        finally:
            db.close()

    def _session_roots(self):
        roots = []
        for home in native_codex.homes():
            home = Path(home).resolve()
            for name in ("sessions", "archived_sessions"):
                root = home / name
                if root.is_symlink():
                    continue
                resolved = root.resolve(strict=False)
                if resolved.is_relative_to(home) and resolved not in roots:
                    roots.append(resolved)
        return roots

    def _allowed_root(self, path):
        candidate = Path(path)
        if candidate.suffix.lower() != ".jsonl" or candidate.is_symlink() or not candidate.is_file():
            raise ValueError("Choose an existing, regular native Codex JSONL session file")
        resolved = candidate.resolve(strict=True)
        for root in self._session_roots():
            if resolved.is_relative_to(root):
                return root
        raise ValueError("Native deletion is limited to configured/default CODEX_HOME sessions and archived_sessions")

    def _validate_session(self, path, session_id, expected_root=None):
        root = self._allowed_root(path)
        if expected_root is not None and root != Path(expected_root).resolve():
            raise ValueError("The session moved outside its validated Codex session root")
        metadata = session_header(path)
        if str(metadata.get("id")) != str(session_id):
            raise ValueError("Session metadata ID does not match the selected chat")
        return root

    def _recovery_path(self, job_id):
        if not re.fullmatch(r"local-[a-f0-9]{32}", str(job_id)):
            raise ValueError("Invalid local native deletion job ID")
        if self.recovery_root.is_symlink():
            raise ValueError("The private Codex recovery folder cannot be a symbolic link")
        root = self.recovery_root.resolve()
        target_dir = self.recovery_root / job_id
        if target_dir.is_symlink():
            raise ValueError("The private Codex recovery entry cannot be a symbolic link")
        if not target_dir.resolve(strict=False).is_relative_to(root):
            raise ValueError("The recovery path escaped the private viewer data folder")
        return target_dir / "session.jsonl"

    def enqueue(self, ids, mode="recovery"):
        if str(mode).strip().casefold() not in ("recovery", "library", "preserve"):
            raise ValueError("Native Codex sessions can only be moved into viewer recovery")
        if not isinstance(ids, list) or not ids or len(ids) > 1000:
            raise ValueError("Select between 1 and 1000 native Codex sessions")
        if any(not isinstance(cid, str) or not cid for cid in ids):
            raise ValueError("Choose valid native Codex session IDs")

        catalog = {str(chat["id"]): chat for chat in self.archive.catalog()}
        settings = self.archive.settings()
        excluded_value = settings.get(EXCLUSIONS_SETTING, [])
        if not isinstance(excluded_value, list):
            raise ValueError("Saved native Codex exclusions have an invalid format")
        excluded = {str(cid) for cid in excluded_value}
        prepared = []
        for session_id in dict.fromkeys(ids):
            with self.connect() as db:
                previous=db.execute('SELECT * FROM native_deletion_jobs WHERE session_id=?',(session_id,)).fetchone()
            if session_id in excluded and not (mode=='library' and previous and previous['state']=='confirmed'):
                raise ValueError("This native Codex session is already in the local deletion archive")
            chat = catalog.get(session_id)
            if not chat or chat.get("kind") != "codex":
                raise ValueError("Choose a discovered native Codex session")
            path = Path(chat.get("path", ""))
            if session_id in excluded:
                if path.resolve()!=Path(previous['recovery_path']).resolve() or str(session_header(path).get('id'))!=session_id:
                    raise ValueError('The retained recovery does not match this session')
                path=Path(previous['source_path']);root=Path(previous['root_path'])
            else:root = self._validate_session(path, session_id)
            prepared.append((session_id, str(path.resolve()), str(root),chat.get('alias') or chat['title']))

        now = time.time()
        with self.lock, self.connect() as db:
            for session_id, source, root, title in prepared:
                old = db.execute(
                    "SELECT id,state FROM native_deletion_jobs WHERE session_id=?", (session_id,)
                ).fetchone()
                if old and old["state"]!='cancelled' and old["state"] in ACTIVE_STATES | FINAL_STATES and not (old["state"]=="confirmed" and mode=="library"):
                    continue
                if old:
                    recovery = self._recovery_path(old["id"])
                    db.execute(
                        """UPDATE native_deletion_jobs SET source_path=?,root_path=?,recovery_path=?,
                           mode=?,title=?,state='queued',error='',updated=?,run='' WHERE session_id=?""",
                        (source, root, str(recovery), mode, title, now, session_id),
                    )
                else:
                    job_id = "local-" + uuid.uuid4().hex
                    recovery = self._recovery_path(job_id)
                    db.execute(
                        """INSERT INTO native_deletion_jobs
                           (id,session_id,source_path,root_path,recovery_path,mode,state,created,updated,title)
                           VALUES(?,?,?,?,?,?,'queued',?,?,?)""",
                        (job_id, session_id, source, root, str(recovery), mode, now, now, title),
                    )
        return self.status()

    def rows(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM native_deletion_jobs ORDER BY created,id"
            )]

    def status(self):
        rows = self.rows()
        counts = {}
        for row in rows:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
        with self.lock:
            guard = dict(self.guard)
            worker_running = bool(self.worker and self.worker.is_alive())
        return {
            "jobs": rows,
            "counts": counts,
            "worker_running": worker_running,
            "process_guard": guard,
            "recovery_root": str(self.recovery_root),
        }

    def action(self, action, ids=None):
        with self.lock, self.connect() as db:
            if action == "run":
                rows = [dict(row) for row in db.execute(
                    "SELECT * FROM native_deletion_jobs WHERE state NOT IN ('confirmed','cancelled')"
                )]
                if not rows:
                    raise ValueError("The native deletion queue is empty")
                if any(row["run"] and row["state"] in ACTIVE_STATES for row in rows):
                    raise ValueError("The native deletion queue is already running")
                if set(ids or []) != {row["id"] for row in rows}:
                    raise ValueError("Review every pending native session before running")
                run_id = uuid.uuid4().hex
                db.execute(
                    """UPDATE native_deletion_jobs SET state='queued',run=?,error='',updated=?
                       WHERE state NOT IN ('confirmed','cancelled')""",
                    (run_id, time.time()),
                )
                self.stop_event.clear()
            elif action in ("pause", "stop"):
                db.execute(
                    """UPDATE native_deletion_jobs SET state='paused',updated=?
                       WHERE state NOT IN ('confirmed','cancelled')""",
                    (time.time(),),
                )
                self.stop_event.set()
            elif action == "remove":
                if not isinstance(ids, list) or not ids:
                    raise ValueError("Select one or more queued native deletion jobs to remove")
                db.executemany(
                    """UPDATE native_deletion_jobs SET state='cancelled',updated=?
                       WHERE id=? AND state IN ('queued','waiting','paused','failed')""",
                    [(time.time(), ident) for ident in ids],
                )
            else:
                raise ValueError("Unknown native deletion queue action")
        if action == "run":
            self.start()
        return self.status()

    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return self.status()
            with self.connect() as db:
                pending = db.execute(
                    "SELECT 1 FROM native_deletion_jobs WHERE run!='' AND state IN ('queued','waiting','running') LIMIT 1"
                ).fetchone()
            if not pending:
                return self.status()
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._loop, name="NativeCodexDeletion", daemon=True)
            self.worker.start()
            return self.status()

    def _loop(self):
        while not self.stop_event.is_set() and not self.archive.cache_stop.is_set():
            try:
                self.tick()
            except Exception as error:
                self._set_active_error(str(error))
            if not self._active_rows():
                return
            self.stop_event.wait(self.poll_interval)

    def _active_rows(self):
        return [row for row in self.rows()
                if row["run"] and row["state"] in ACTIVE_STATES]

    def _record_guard(self, running=None, error=""):
        with self.lock:
            self.guard = {"checked": time.time(), "codex_running": running, "error": error}

    def _check_process(self):
        try:
            running = bool(self.process_running())
        except Exception as error:
            self._record_guard(None, str(error))
            raise _Deferred(f"Could not confirm Codex is closed; deletion is deferred: {error}") from error
        self._record_guard(running, "")
        if running:
            raise _Deferred("Codex is running; local deletion is deferred")

    def _set_job_state(self, row, state, error="", only_active=False):
        with self.lock, self.connect() as db:
            predicate = " AND state IN ('queued','waiting','running')" if only_active else ""
            db.execute(
                "UPDATE native_deletion_jobs SET state=?,error=?,updated=? WHERE id=? AND run=?" + predicate,
                (state, error[:2000], time.time(), row["id"], row["run"]),
            )

    def _set_active_error(self, error):
        with self.lock, self.connect() as db:
            db.execute(
                """UPDATE native_deletion_jobs SET error=?,updated=?
                   WHERE run!='' AND state IN ('queued','waiting','running')""",
                (error[:2000], time.time()),
            )

    def _job_is_running(self, row):
        with self.lock, self.connect() as db:
            current = db.execute(
                "SELECT state,run FROM native_deletion_jobs WHERE id=?", (row["id"],)
            ).fetchone()
            return bool(current and current["state"] == "running" and current["run"] == row["run"])

    def tick(self):
        with self.tick_lock:
            rows = self._active_rows()
            if not rows:
                return self.status()
            try:
                self._check_process()
            except _Deferred as error:
                for row in rows:
                    self._set_job_state(row, "waiting", str(error), only_active=True)
                return self.status()

            for row in rows:
                if self.stop_event.is_set() or self.archive.cache_stop.is_set():
                    return self.status()
                with self.lock, self.connect() as db:
                    current = db.execute(
                        "SELECT state,run FROM native_deletion_jobs WHERE id=?", (row["id"],)
                    ).fetchone()
                    if not current or current["state"] not in ACTIVE_STATES or current["run"] != row["run"]:
                        continue
                    db.execute(
                        "UPDATE native_deletion_jobs SET state='running',error='',updated=? WHERE id=?",
                        (time.time(), row["id"]),
                    )
                try:
                    self._process_one(row)
                    self._set_job_state(row, "confirmed")
                except _Deferred as error:
                    self._set_job_state(row, "waiting", str(error), only_active=True)
                except Exception as error:
                    self._set_job_state(row, "failed", str(error), only_active=True)
            return self.status()

    def _check_stored_paths(self, row):
        source = Path(row["source_path"])
        root = Path(row["root_path"]).resolve()
        if source.suffix.lower() != ".jsonl":
            raise ValueError("Native deletion is limited to Codex JSONL sessions")
        allowed = set(self._session_roots())
        if root not in allowed:
            raise ValueError("The queued source is outside configured/default CODEX_HOME session roots")
        if source.resolve(strict=False).is_relative_to(root) is False:
            raise ValueError("The queued source escaped its validated Codex session root")
        expected = self.recovery_root / row["id"] / "session.jsonl"
        if Path(row["recovery_path"]).resolve(strict=False) != expected.resolve(strict=False):
            raise ValueError("The queued recovery path is outside private viewer recovery")
        return source, root, expected

    def _copy_recovery(self, source, recovery, session_id):
        before = _stat_key(source)
        session_header(source)
        if self.recovery_root.is_symlink():
            raise ValueError("The private Codex recovery folder cannot be a symbolic link")
        recovery.parent.mkdir(parents=True, exist_ok=True)
        if recovery.parent.is_symlink() or not recovery.parent.resolve().is_relative_to(self.recovery_root.resolve()):
            raise ValueError("The recovery path escaped the private viewer data folder")
        if recovery.is_symlink():
            raise ValueError("The private recovery target cannot be a symbolic link")
        if recovery.exists():
            metadata = session_header(recovery)
            if str(metadata.get("id")) != session_id or _digest(recovery) != _digest(source):
                raise ValueError("A different file already occupies this session's recovery path")
            return _digest(recovery)

        temporary = recovery.with_name("session.jsonl." + uuid.uuid4().hex + ".tmp")
        try:
            shutil.copy2(source, temporary)
            with temporary.open("rb+") as stream:
                os.fsync(stream.fileno())
            copied_hash = _digest(temporary)
            source_hash = _digest(source)
            if before != _stat_key(source) or source_hash != copied_hash:
                raise ValueError("The session changed during backup; the original was left in place")
            metadata = session_header(temporary)
            if str(metadata.get("id")) != session_id:
                raise ValueError("The recovery copy does not match the selected session ID")
            if recovery.exists():
                if _digest(recovery) != copied_hash:
                    raise ValueError("A different file already occupies this session's recovery path")
            else:
                os.replace(temporary, recovery)
            if _digest(recovery) != copied_hash:
                raise ValueError("The recovery copy failed its final integrity check")
            return copied_hash
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _persist_exclusion(self, session_id):
        settings = self.archive.settings()
        values = settings.get(EXCLUSIONS_SETTING, [])
        if not isinstance(values, list):
            raise ValueError("Saved native Codex exclusions have an invalid format")
        excluded = sorted({str(value) for value in values} | {str(session_id)})
        self.archive.save_settings({EXCLUSIONS_SETTING: excluded})
        saved = self.archive.settings().get(EXCLUSIONS_SETTING, [])
        if not isinstance(saved, list) or str(session_id) not in {str(value) for value in saved}:
            raise OSError("The native Codex exclusion was not durably saved")

    @staticmethod
    def _same_path(left, right):
        return Path(left).resolve(strict=False) == Path(right).resolve(strict=False)

    def _retarget_viewer_source(self, session_id, source, recovery):
        recovery = Path(recovery).resolve(strict=True)
        metadata = session_header(recovery)
        if str(metadata.get("id")) != str(session_id):
            raise ValueError("The recovery copy does not match the selected session ID")
        info = recovery.stat()
        fingerprint = f"{info.st_mtime_ns}:{info.st_size}"
        original = Path(source).resolve(strict=False)
        matched_manifests = []
        updated_chat = False

        with self.archive.lock, self.archive.connect() as db:
            chat = db.execute("SELECT * FROM chats WHERE id=?", (session_id,)).fetchone()
            if chat:
                if not self._same_path(chat["path"], original) and not self._same_path(chat["path"], recovery):
                    raise ValueError("The viewer chat points to a different source; refusing to retarget it")
                db.execute(
                    "UPDATE chats SET path=?,fingerprint=?,folder=? WHERE id=?",
                    (str(recovery), fingerprint, str(recovery.parent), session_id),
                )
                updated_chat = True

            manifests = db.execute(
                "SELECT manifest,metadata,path FROM manifest_entries WHERE cid=?", (session_id,)
            ).fetchall()
            for item in manifests:
                if not self._same_path(item["path"], original) and not self._same_path(item["path"], recovery):
                    continue
                entry = json.loads(item["metadata"] or "{}")
                if not isinstance(entry, dict):
                    raise ValueError("The saved native manifest metadata is invalid")
                entry["native_recovery"] = {
                    "session_id": str(session_id),
                    "path": str(recovery),
                    "original_path": str(original),
                    "manifest": item["manifest"],
                }
                db.execute(
                    "UPDATE manifest_entries SET metadata=?,path=?,available=1 WHERE cid=? AND manifest=?",
                    (json.dumps(entry, ensure_ascii=False), str(recovery), session_id, item["manifest"]),
                )
                matched_manifests.append(entry)

            if not updated_chat and not matched_manifests:
                raise ValueError("No viewer chat or manifest points to this native session")

        self.archive.revision += 1
        live = dict(self.archive.live_sources.get(session_id, {}))
        if not live:
            catalog_item = next((item for item in self.archive.catalog() if item["id"] == session_id), None)
            if catalog_item:
                live.update(catalog_item)
        if not live and matched_manifests:
            entry = matched_manifests[0]
            live.update(
                id=session_id,
                title=entry.get("title") or recovery.stem,
                url="",
                created=0,
                updated=info.st_mtime,
                kind="codex",
                kind_evidence="Native Codex session metadata",
                project="",
                count=0,
                loaded=False,
            )
        if updated_chat:
            chat_count = chat["count"] or 0
            live.update(count=chat_count, loaded=True)
        live.update(path=str(recovery), fingerprint=fingerprint, folder=str(recovery.parent))
        self.archive.live_sources[session_id] = live
        self.archive.publish_sources([live])

    def _process_one(self, row):
        session_id = row["session_id"]
        source, root, recovery = self._check_stored_paths(row)
        source_key = None
        source_hash = None
        if source.exists():
            self._validate_session(source, session_id, root)
            source_key = _stat_key(source)
            source_hash = self._copy_recovery(source, recovery, session_id)
        else:
            if not recovery.is_file() or recovery.is_symlink():
                raise FileNotFoundError("The original and its recovery copy are both missing")
            metadata = session_header(recovery)
            if str(metadata.get("id")) != session_id:
                raise ValueError("The saved recovery copy does not match the selected session")
            source_hash = _digest(recovery)

        if self.stop_event.is_set() or self.archive.cache_stop.is_set():
            raise _Deferred("The queue stopped after backup; the original remains in place")
        if not self._job_is_running(row):
            raise _Deferred("The job was paused or removed after backup; the original remains in place")

        # Serialize exclusion and discovery registration. The viewer DB and cache
        # are retargeted before unlink, so a restart can always render recovery.
        with self.session_lock:
            if not self._job_is_running(row):
                raise _Deferred("The job was paused or removed before moving the original")
            if self.stop_event.is_set() or self.archive.cache_stop.is_set():
                raise _Deferred("The queue stopped before moving the original")
            self._check_process()
            self._persist_exclusion(session_id)
            self._retarget_viewer_source(session_id, source, recovery)

            if source.exists():
                if not self._job_is_running(row):
                    raise _Deferred("The job was paused or removed before moving the original")
                if self.stop_event.is_set() or self.archive.cache_stop.is_set():
                    raise _Deferred("The queue stopped before moving the original")
                self._validate_session(source, session_id, root)
                if source_key != _stat_key(source) or source_hash != _digest(source):
                    raise ValueError("The session changed after backup; the original was left in place")
                if _digest(recovery) != source_hash:
                    raise ValueError("The recovery copy no longer matches the original session")
                self._check_process()
                source.unlink()
                if source.exists():
                    raise OSError("The original session is still present after moving to recovery")

        if row['mode']=='library':self.archive.remove_local_chat(session_id)
        else:self.archive.organize(session_id, {"trashed": 1})

    def close(self):
        self.stop_event.set()
        worker = self.worker
        if worker and worker is not threading.current_thread():
            worker.join(timeout=7)
