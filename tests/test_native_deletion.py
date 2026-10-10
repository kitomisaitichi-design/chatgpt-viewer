import errno
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from native_codex import NativeCodex
from native_deletion import EXCLUSIONS_SETTING, NativeDeletionQueue
from viewer import Archive


class NativeDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "codex"
        self.session_id = "native-session-12345678"
        self.attachment = self.base / "attached-image.png"
        self.attachment.write_bytes(b"native attachment provenance")
        self.source = self.home / "sessions" / "2026" / "10" / "07" / "rollout.jsonl"
        self.source.parent.mkdir(parents=True)
        self.source.write_text(
            "\n".join([
                json.dumps({"type": "session_meta", "payload": {
                    "id": self.session_id, "originator": "codex_cli_rs",
                    "timestamp": "2026-10-07T12:00:00Z",
                }}),
                json.dumps({"type": "response_item", "timestamp": "2026-10-07T12:00:01Z", "payload": {
                    "type": "message", "role": "user", "content": [
                        {"type": "input_text", "text": "Review this image"},
                        {"type": "input_image", "image_url": self.attachment.as_uri()},
                    ],
                }}),
                json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant",
                    "phase": "final_answer", "content": [{"type": "output_text", "text": "Answer"}]}}),
                "",
            ]),
            encoding="utf-8",
        )
        self.original_bytes = self.source.read_bytes()
        self.archive = Archive(self.base / "viewer-data", background_process=False)
        self.archive.enable_ui_cache()
        if self.archive.cache_thread:
            self.archive.cache_thread.join(timeout=5)
        self.codex = None
        self.env_patch = patch.dict(os.environ, {"CODEX_HOME": str(self.home)})
        self.env_patch.start()
        self.codex = NativeCodex(self.archive)
        with patch("native_codex.homes", return_value=[self.home]):
            self.codex.discover()
        item = next(self.archive.read_items(self.source))
        info = self.source.stat()
        self.archive.store(item, self.source, f"{info.st_mtime_ns}:{info.st_size}", self.home, {})
        self.archive.publish_sources([self.archive.live_sources[self.session_id]])

    def tearDown(self):
        if self.codex:
            self.codex.close()
        self.archive.close()
        self.env_patch.stop()
        self.temp.cleanup()

    def queue(self):
        return NativeDeletionQueue(
            self.archive,
            session_lock=self.codex.session_lock,
        )

    def test_confirmation_durable_queue_and_local_delete_without_codex_shutdown(self):
        queue = self.queue()
        queue.enqueue([self.session_id], mode="recovery")
        job = queue.rows()[0]
        self.assertEqual(job["state"], "queued")
        self.assertTrue(job["id"].startswith("local-"))
        with self.assertRaisesRegex(ValueError, "Review every pending"):
            queue.action("run")
        with self.assertRaisesRegex(ValueError, "Review every pending"):
            queue.action("run", [job["id"], "remote-job-123"])

        # Reopening the viewer-owned queue retains the reviewed job and its ID.
        queue = self.queue()
        self.assertEqual(queue.rows()[0]["id"], job["id"])
        with patch.object(queue, "start"):
            queue.action("run", [job["id"]])

        original_unlink = Path.unlink
        unlink_observed = []

        def check_retained_copy_before_unlink(path, *args, **kwargs):
            if path == self.source:
                self.assertIn(self.session_id, self.archive.settings()[EXCLUSIONS_SETTING])
                with self.archive.connect() as db:
                    stored = db.execute("SELECT path FROM chats WHERE id=?", (self.session_id,)).fetchone()
                    manifest = db.execute(
                        "SELECT path,available FROM manifest_entries WHERE cid=? LIMIT 1", (self.session_id,)
                    ).fetchone()
                self.assertEqual(Path(stored["path"]), Path(queue.rows()[0]["recovery_path"]))
                self.assertEqual(Path(manifest["path"]), Path(queue.rows()[0]["recovery_path"]))
                self.assertTrue(manifest["available"])
                self.assertTrue(Path(queue.rows()[0]["recovery_path"]).is_file())
                unlink_observed.append(True)
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", new=check_retained_copy_before_unlink):
            completed = queue.tick()["jobs"][0]
        self.assertTrue(unlink_observed)
        recovery = Path(completed["recovery_path"])
        self.assertEqual(completed["state"], "confirmed")
        self.assertFalse(self.source.exists())
        self.assertEqual(recovery.read_bytes(), self.original_bytes)
        self.assertIn(self.session_id, self.archive.settings()[EXCLUSIONS_SETTING])
        chat = next(chat for chat in self.archive.catalog() if chat["id"] == self.session_id)
        self.assertEqual(chat["trashed"], 1)
        self.assertEqual(Path(chat["path"]), recovery)
        with self.archive.connect() as db:
            stored = db.execute("SELECT path,fingerprint FROM chats WHERE id=?", (self.session_id,)).fetchone()
            manifests = db.execute(
                "SELECT metadata,path,available FROM manifest_entries WHERE cid=?", (self.session_id,)
            ).fetchall()
        self.assertEqual(Path(stored["path"]), recovery)
        self.assertEqual(stored["fingerprint"], f"{recovery.stat().st_mtime_ns}:{recovery.stat().st_size}")
        self.assertTrue(manifests)
        self.assertTrue(all(Path(row["path"]) == recovery and row["available"] for row in manifests))
        self.assertTrue(all(json.loads(row["metadata"])["native_recovery"]["original_path"] == str(self.source.resolve()) for row in manifests))
        self.assertEqual(Path(self.archive.live_sources[self.session_id]["path"]), recovery)
        self.assertEqual(Path(self.archive.ui_cache["chats"][self.session_id]["path"]), recovery)
        raw, rendered_source = self.archive.source_data(self.session_id)
        self.assertEqual(rendered_source, recovery)
        self.assertEqual(self.archive.asset(self.session_id, self.attachment.as_uri(), indexed=False), self.attachment)
        self.assertEqual(self.archive.foreground_page(self.session_id)["total"], 2)

    def test_only_locked_selected_file_waits_and_retries_while_codex_stays_open(self):
        queue=self.queue()
        queue.enqueue([self.session_id], mode="library")
        job=queue.rows()[0]
        with patch.object(queue, "start"):
            queue.action("run", [job["id"]])
        original_unlink=Path.unlink

        def selected_file_locked(path, *args, **kwargs):
            if path == self.source:
                raise OSError(errno.EBUSY, "Selected Codex JSONL still held by another process")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", new=selected_file_locked):
            waiting=queue.tick()["jobs"][0]
        self.assertEqual(waiting["state"], "waiting")
        self.assertIn("This Codex session file is in use", waiting["error"])
        self.assertTrue(self.source.exists())
        self.assertEqual(Path(waiting["recovery_path"]).read_bytes(), self.original_bytes)
        completed=queue.tick()["jobs"][0]
        self.assertEqual(completed["state"], "confirmed")
        self.assertFalse(self.source.exists())
        self.assertEqual(self.archive.catalog(), [])

    def test_exclusion_survives_restart_and_discovery_skips_session(self):
        queue = self.queue()
        queue.enqueue([self.session_id])
        job = queue.rows()[0]
        with patch.object(queue, "start"):
            queue.action("run", [job["id"]])
        queue.tick()
        self.assertFalse(self.source.exists())
        recovery = Path(job["recovery_path"])
        raw, rendered_source = self.archive.source_data(self.session_id)
        self.assertEqual(rendered_source, recovery)
        self.assertEqual(len(raw["messages"]), 2)

        self.archive.close()
        restarted = Archive(self.base / "viewer-data", background_process=False)
        try:
            with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}):
                native = NativeCodex(restarted)
                with patch("native_codex.homes", return_value=[self.home]):
                    native.discover()
                self.assertEqual(native.status()["found"], 0)
                recovered_chat = next(chat for chat in restarted.catalog() if chat["id"] == self.session_id)
                self.assertEqual(Path(recovered_chat["path"]), recovery)
                self.assertEqual(restarted.foreground_page(self.session_id)["total"], 2)
                self.assertEqual(restarted.asset(self.session_id, self.attachment.as_uri(), indexed=False), self.attachment)
                native.close()
            self.assertIn(self.session_id, restarted.settings()[EXCLUSIONS_SETTING])
        finally:
            restarted.close()

    def test_discovery_rechecks_exclusion_immediately_before_registration(self):
        with self.archive.lock, self.archive.connect() as db:
            db.execute("DELETE FROM manifest_entries WHERE cid=?", (self.session_id,))
        self.archive.live_sources.pop(self.session_id, None)
        calls = 0

        def settings_changed_after_snapshot():
            nonlocal calls
            calls += 1
            if calls == 1:
                return {}
            return {EXCLUSIONS_SETTING: [self.session_id]}

        with patch.object(self.archive, "settings", side_effect=settings_changed_after_snapshot):
            self.codex.state.update(found=0, errors=[])
            with patch("native_codex.homes", return_value=[self.home]):
                self.codex.discover()
        self.assertEqual(self.codex.status()["found"], 0)
        with self.archive.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT 1 FROM manifest_entries WHERE cid=?", (self.session_id,)
            ).fetchone())

    def test_library_and_preserve_modes_are_distinct(self):
        queue = self.queue()
        self.assertEqual(queue.enqueue([self.session_id], mode="library")["jobs"][0]["mode"], "library")
        queue.action("remove", [queue.rows()[0]["id"]])
        self.assertEqual(queue.enqueue([self.session_id], mode="preserve")["jobs"][0]["mode"], "preserve")

    def test_delete_local_mode_removes_catalog_indexes_and_prevents_rediscovery(self):
        queue=self.queue();queue.enqueue([self.session_id],mode='library');job=queue.rows()[0]
        with patch.object(queue,'start'):queue.action('run',[job['id']])
        queue.tick();self.assertEqual(queue.rows()[0]['state'],'confirmed')
        self.assertFalse(self.source.exists());self.assertTrue(Path(job['recovery_path']).is_file())
        self.assertEqual(self.archive.catalog(),[]);self.assertNotIn(self.session_id,self.archive.ui_cache['chats'])
        self.assertIn(self.session_id,self.archive.state()['removed'])
        self.source.write_bytes(self.original_bytes)
        with patch('native_codex.homes',return_value=[self.home]):self.codex.discover()
        self.assertEqual(self.archive.catalog(),[])
        self.assertTrue(self.attachment.exists(),'Referenced workspace files are not owned session files')

    def test_remove_previously_preserved_native_copy(self):
        queue=self.queue();queue.enqueue([self.session_id],mode='preserve');job=queue.rows()[0]
        with patch.object(queue,'start'):queue.action('run',[job['id']])
        queue.tick();self.assertTrue(self.archive.catalog())
        queue.enqueue([self.session_id],mode='library')
        with patch.object(queue,'start'):queue.action('run',[job['id']])
        queue.tick();self.assertEqual(queue.rows()[0]['state'],'confirmed');self.assertEqual(self.archive.catalog(),[])

    def test_default_codex_home_is_a_validated_session_root(self):
        fallback = self.base / "default-codex"
        fallback_source = fallback / "sessions" / "fallback.jsonl"
        fallback_source.parent.mkdir(parents=True)
        fallback_source.write_text(
            json.dumps({"type": "session_meta", "payload": {
                "id": "fallback-native-session", "originator": "codex_cli_rs",
            }}) + "\n",
            encoding="utf-8",
        )
        self.archive.register_manifest(
            {
                "id": "fallback-native-session", "title": "Fallback session",
                "json": fallback_source.name, "chat_kind": "codex",
            },
            fallback_source.parent / "native-codex-index.json",
            fallback_source.parent,
        )
        queue = self.queue()
        with patch("native_codex.homes", return_value=[self.home, fallback]):
            result = queue.enqueue(["fallback-native-session"], mode="preserve")
        self.assertTrue(result["jobs"][0]["id"].startswith("local-"))
        self.assertEqual(Path(result["jobs"][0]["source_path"]), fallback_source.resolve())

    def test_outside_codex_home_session_is_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        outside_session = outside / "outside.jsonl"
        outside_session.write_text(
            json.dumps({"type": "session_meta", "payload": {
                "id": "outside-session-12345678", "originator": "codex_cli_rs",
            }}) + "\n",
            encoding="utf-8",
        )
        self.archive.register_manifest(
            {
                "id": "outside-session-12345678",
                "title": "Outside session",
                "json": outside_session.name,
                "chat_kind": "codex",
            },
            outside / "native-codex-index.json",
            outside,
        )
        queue = self.queue()
        with self.assertRaisesRegex(ValueError, "limited to configured/default CODEX_HOME"):
            queue.enqueue(["outside-session-12345678"])
        self.assertTrue(outside_session.is_file())
        self.assertEqual(queue.rows(), [])


if __name__ == "__main__":
    unittest.main()
