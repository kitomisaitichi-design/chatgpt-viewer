#!/usr/bin/env python3
r"""Read-only regression probes for the portable v1.1.28 codebase.

Run from the application root:
    runtime\python.exe -B docs\verify-architecture-v1.1.28.py

The script never reads or opens the real .viewer-data. It creates and removes
all test exports, databases, sockets, and companion credentials in temporary
directories. By default it runs the concurrency and recovery suites too.
Use --quick for the original core fixtures alone. Known defects are reported
as observations, not asserted forever. The separate frontend JS fixture must
be run manually in a throwaway browser tab, as documented in the architecture.
"""
from __future__ import annotations

import http.cookiejar
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from browser_companion import BrowserCompanion
from find_text import conversation_matches
from viewer import Archive, Server, VERSION, bounded_message_page


def say(name, **facts):
    print(name + ": " + json.dumps(facts, sort_keys=True))


def fixtures():
    with tempfile.TemporaryDirectory(prefix="offline-viewer-architecture-") as directory:
        base = pathlib.Path(directory)
        source = base / "exports"
        source.mkdir()
        (source / "sample.md").write_text(
            "# Example\n## User\nFind the orange marmalade.\n"
            "## Assistant\nOrange marmalade is present.\n", encoding="utf-8"
        )
        nodes = {
            "u": {"id": "u", "parent": None, "children": ["a", "b"],
                  "message": {"author": {"role": "user"},
                              "content": {"content_type": "text", "parts": ["choose a branch"]}}},
            "a": {"id": "a", "parent": "u", "children": [],
                  "message": {"author": {"role": "assistant"}, "channel": "final",
                              "content": {"content_type": "text", "parts": ["main answer"]}}},
            "b": {"id": "b", "parent": "u", "children": [],
                  "message": {"author": {"role": "assistant"}, "channel": "final",
                              "content": {"content_type": "text", "parts": ["other answer"]}}},
        }
        branch = source / "branch.json"
        export = {"id": "branch-audit", "title": "Branch fixture", "mapping": nodes, "current_node": "a"}
        branch.write_text(json.dumps(export), encoding="utf-8")
        archive = Archive(base / "temporary-db", background_process=False)
        try:
            archive.scan(source, 0)
            assert len(archive.catalog()) == 2 and not archive.status["errors"]
            mdid = next(c["id"] for c in archive.catalog() if c["title"] == "Example")
            assert [m["role"] for m in archive.page(mdid)["messages"]] == ["user", "assistant"]
            assert len(conversation_matches(archive, mdid, "orange marmalade")["results"]) == 2
            assert len(archive.search("orange marmalade", "exact")["results"]) == 2
            assert archive.branch_page("branch-audit", "b")["messages"][-1]["text"] == "other answer"
            assert archive.choose_version("branch-audit", "b") == "b"
            say("import-and-branches", indexed=len(archive.catalog()), branch="pass", search="pass")

            archive.scan(source, 0)
            assert archive.status["indexed"] == 0 and archive.status["cached"] == 2
            export["mapping"]["a"]["message"]["content"]["parts"] = ["LONG TEXT"] * 12000
            branch.write_text(json.dumps(export), encoding="utf-8")
            archive.scan(source, 0)
            original = archive.page("branch-audit")["messages"][-1]["text"]
            page = bounded_message_page(archive.page("branch-audit"), 8192)
            partial = page["messages"][-1]
            assert partial["text_complete"] is False
            rebuilt = partial["text"]
            offset = partial["text_next"]
            while offset < len(original):
                fragment = archive.message_fragment("branch-audit", partial["seq"], offset, budget=65536)
                assert fragment["next_offset"] > offset
                rebuilt += fragment["text"]
                offset = fragment["next_offset"]
            assert rebuilt == original
            say("incremental-and-fragments", unchanged_cached=2, changed_indexed=1, exact_rebuild=True)

            branch.write_text("{BROKEN", encoding="utf-8")
            archive.scan(source, 0)
            assert archive.status["errors"]
            assert archive.page("branch-audit")["messages"][-1]["text"] == original
            export["mapping"]["a"]["message"]["content"]["parts"] = ["restored answer"]
            branch.write_text(json.dumps(export), encoding="utf-8")
            archive.scan(source, 0)
            assert not archive.status["errors"]
            assert archive.page("branch-audit")["messages"][-1]["text"] == "restored answer"
            say("corruption-and-recovery", retained_previous_index=True, recovered=True)

            phrase = " ".join("term%03d" % i for i in range(42))
            (source / "boundary.md").write_text(
                "# Boundary\n## User\n" + ("z" * 987) + " " + phrase
                + "\n## Assistant\ncomplete\n", encoding="utf-8"
            )
            archive.scan(source, 0)
            boundary_id = next(c["id"] for c in archive.catalog() if c["title"] == "Boundary")
            exact = len(archive.search(phrase, "exact")["results"])
            found = len(conversation_matches(archive, boundary_id, phrase)["results"])
            assert found == 1
            say("known-phrase-recall-gap", exact_archive_hits=exact,
                complete_conversation_find_hits=found, defect_open=(exact == 0))

            # A completed remote-status check must be eligible for a fresh check,
            # but the shipped browser companion reuses it for up to 15 minutes.
            queue = SimpleNamespace(archive=archive, chat_account=lambda cid: (str(source), "scope-a"))
            companion = BrowserCompanion(queue)
            first = companion.check("branch-audit")
            with archive.connect() as db:
                db.execute("UPDATE browser_checks SET done=1 WHERE id=?", (first["id"],))
            second = companion.check("branch-audit")
            say("known-companion-dedupe-gap", first_id_reused=(first["id"] == second["id"]),
                defect_open=(first["id"] == second["id"]))

            server = Server(("127.0.0.1", 0), archive)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = "http://127.0.0.1:" + str(server.server_port)
            try:
                try:
                    urllib.request.urlopen(base_url + "/api/health", timeout=3).close()
                    raise AssertionError("Unauthenticated health request was accepted")
                except urllib.error.HTTPError as error:
                    assert error.code == 403
                opener = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                with opener.open(base_url + "/?token=" + server.token, timeout=3) as response:
                    response.read()
                with opener.open(base_url + "/api/health", timeout=3) as response:
                    assert json.load(response)["version"] == VERSION
                with opener.open(base_url + "/api/messages?id=branch-audit", timeout=3) as response:
                    assert json.load(response)["total"] == 2
                say("isolated-http", missing_cookie=403, authenticated=200, messages=200)
            finally:
                server.shutdown()
                server.server_close()

            archive.remove_local_chat(mdid)
            archive.scan(source, 0)
            assert mdid not in {c["id"] for c in archive.catalog()}
            say("local-tombstone", remains_removed_after_scan=True)
        finally:
            archive.close()


def old_schema():
    with tempfile.TemporaryDirectory(prefix="offline-viewer-legacy-schema-") as directory:
        data = pathlib.Path(directory)
        db = sqlite3.connect(data / "archive.sqlite3")
        try:
            with db:
                db.execute("CREATE TABLE chats(id TEXT PRIMARY KEY,title TEXT,url TEXT,"
                           "created REAL,updated REAL,kind TEXT,project TEXT,path TEXT,"
                           "fingerprint TEXT,count INTEGER,folder TEXT)")
                db.execute("CREATE TABLE messages(cid TEXT,seq INTEGER,role TEXT,channel TEXT,"
                           "text TEXT,time REAL,visible INTEGER,PRIMARY KEY(cid,seq))")
                db.execute("CREATE TABLE organization(cid TEXT PRIMARY KEY,category TEXT DEFAULT '',"
                           "pinned INTEGER DEFAULT 0,position REAL DEFAULT 0,alias TEXT DEFAULT '')")
                db.execute("INSERT INTO chats VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           ("legacy", "Old thread", "", 0, 0, "chat", "", "", "", 1, ""))
                db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                           ("legacy", 0, "user", "", "preserved fixture", 0, 1))
        finally:
            db.close()
        archive = Archive(data, background_process=False)
        try:
            assert archive.page("legacy")["messages"][0]["text"] == "preserved fixture"
            with archive.connect() as db:
                columns = {r["name"] for r in db.execute("PRAGMA table_info(messages)")}
                org = {r["name"] for r in db.execute("PRAGMA table_info(organization)")}
            assert "extras" in columns and "trashed" in org
            say("legacy-schema", original_message_preserved=True, migrated=True)
        finally:
            archive.close()


if __name__ == "__main__":
    fixtures()
    old_schema()
    print("All isolated fixture directories removed; live archive was never opened.")
    if "--quick" not in sys.argv:
        scripts = (
            "verify-concurrency-v1.1.28.py",
            "verify-recovery-v1.1.28.py",
        )
        for script in scripts:
            print("Running extended isolated audit: " + script, flush=True)
            subprocess.run(
                [sys.executable, "-B", str(pathlib.Path(__file__).parent / script)],
                cwd=str(ROOT), check=True, timeout=120,
            )
        print("Extended Python audit probes passed; live archive was never opened.")
