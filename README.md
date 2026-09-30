# Offline Chat Viewer · v1.0.13

A local ChatGPT-style reader for your Markdown and JSON exports. The standard viewer has no package-install step, cloud service, subscription, or CDN dependency. Windows x64 Python is included in the download.

## Start on Windows / Edge

1. On Windows, right-click the downloaded ZIP → **Properties → Unblock → Apply**, if that checkbox is shown. Then **extract the entire ZIP** into a normal folder. Do not run it from inside the ZIP.
2. Double-click **START-VIEWER.bat**. It opens your default browser. Keep its console window open while reading.
3. The first background scan starts automatically: the viewer folder first, then nearby folders below up to **two parent folders**. Chats appear progressively; it never waits for the entire tree to be enumerated. Put the viewer near your export folder for convenient discovery.
4. For a precise location, click **Export folders → Browse…**, choose your exporter output folder, select `0 · only this folder` (automatically selected after Browse) or another upward depth, and click **Scan & index**.
5. Click any conversation. The selected chat has priority over indexing. Titles from the manifest can appear before their content is indexed. It displays the latest **five messages first**, then fills the reading page to your configured size (100 by default) with small background requests. Older messages load as you scroll upward.

Startup downloads at most five titles, including the remembered chat or the chat in a saved URL. Remaining titles arrive through a separate queue of up to 25 titles / about 16 KiB per response. If a batch times out, it retries with five. You can read, search, or open folder controls while this queue continues. Larger responses are compressed locally; the browser does not receive the entire catalog in one startup response.

If Edge is not your default browser, copy the launch URL printed in the console into Edge. It contains a local session token; the ordinary URL works after that first visit in the same browser. Opening the HTML file directly does not run folder discovery.

Closing the console stops the server. Settings → Stop viewer also stops it. Double-click the launcher to reopen. The bundled runtime is Windows x64; macOS/Linux can use Python 3.10+ with `python3 viewer.py` or START-VIEWER.command. Windows ARM64 can use its x64 emulation or a full Python installation.

When updating, close the old viewer console, replace the app files, **keep `.viewer-data`**, and reopen START-VIEWER.bat. Your existing index and organization remain available. Type corrections update automatically without rebuilding message contents. If loading still stalls, run **CHECK-VIEWER.bat** while the viewer is open and attach **VIEWER-DIAGNOSTICS.json**. The report includes response lengths, received bytes, and transfer timings, with no conversation text, titles, folder paths, or session tokens.

## Discovery and formats

- Reads your English Autopilot export: individual `.md` / `.json` conversations, `conversation-index.json`, and `portable-state*.json` metadata.
- Also reads standard ChatGPT `conversations.json` arrays, simple `{title, messages:[...]}` JSON, and explicit-role Codex `.jsonl` session records.
- **MD and JSON copies merge by conversation ID. JSON is preferred**, preserving its selected branch and message metadata. Additional JSON branches are available under **Branches**.
- `conversation-index.json` enriches matching files with original links, project names, chat kind, and calendar dates. Manifest entries with an existing saved file appear before full-text indexing finishes and can be opened immediately. Entries without files are counted separately in Discovery notes.
- **Pause discovery / Stop current scan** cancels the background worker; an interrupted transaction rolls back safely. Cached chats remain available. A new folder request cancels the previous scan and starts the new scope; it is never silently ignored. Pause persists across restarts.
- Export folders shows the scan boundary, current folder/file, files discovered/checked, changed chats, and unchanged files.
- A separate background process and a file-path queue capped at the discovery limit let discovery and indexing overlap without sharing the foreground reader’s Python interpreter. A persistent per-file checkpoint skips unchanged chats and unrelated documents on later scans, including after restart.
- Scans additional folders when you choose them; previously indexed conversations remain cached. Original exports are never rewritten or deleted.
- Chat/Work/Codex labels use saved product metadata. Work model markers include -wm, Luna, Terra, Astra, and Sol 6/6.1. Luna alone does not imply Work when the saved account metadata identifies a free account. Model-based classifications are identified as inferences in the chat tooltip. An explicit saved Work label still takes precedence. Native Codex session records identify Codex; Codex tools used inside Work do not change its type. Exporter labels normal-chat/project-chat normalize to Chat; project membership is independent of product type. Existing cached receipts and bounded source headers update types automatically. Manual overrides remain available and take precedence. Titles and code blocks are not treated as evidence of chat type.
- Tool output, analysis channels, and reasoning-summary objects are hidden initially. **Tool details** reveals them. The original content stays in the index and source file.
- Symlinks, Windows system folders, hidden caches, dependencies, model files, the viewer index, downloaded attachment folders, and failed-download reports are skipped. Automatic upward traversal stops before a drive/filesystem root. Downward traversal is limited to 24 directory levels / 25,000 directories / 100,000 candidate files; any limit appears in Discovery notes.
- Individual source files over 512 MiB are reported as skipped. Huge standard `conversations.json` arrays are parsed in memory on their first scan; prefer the exporter's individual files for large archives.
- Markdown export role headings can be ambiguous if the original message itself contains an identical unescaped `## Assistant` / `## You` heading. The JSON copy resolves this ambiguity when present.

## Reading

- User bubbles, assistant messages, Markdown tables, lists, quotes, fenced code and **offline KaTeX math** render in the chat column.
- **Per-message model receipts** show the saved answered model (`resolved_model_slug`, then `model_slug`) and thinking effort. A differing per-message `default_model_slug` produces a reroute badge, except for Auto selections. Hover/click shows/copies the raw metadata. A conversation-wide current default is not assumed to describe past turns.
- **Previous/next version arrows** appear for edited user messages and regenerated assistant replies when the JSON graph preserves real alternatives. Switching changes the continuation to that saved branch. Tools, hidden nodes, and commentary are traversed without being mistaken for extra response versions.
- Code and messages have copy buttons. Long tables scroll horizontally.
- The main view holds at most 300 messages during normal selected-branch browsing. Older/newer pages load in both directions. The browser can skip rendering offscreen message contents.
- **Latest messages ↓** jumps to the last page; **Jump to first message** jumps to the beginning.
- **Continue original chat ↗** at the end opens the saved online conversation URL. Continuing requires internet and the original account's access; it does not send offline edits to ChatGPT.
- Saved local image paths display when files are present. Other linked local files download. Remote images are represented by their reference and are not fetched in the background. Asset pointers without a saved binary remain references.
- **Download source** downloads the exact indexed MD/JSON file. It is a source download, not an export of your current branch preview.
- Alternate JSON branches and per-message versions use the same 100-message paging and 300-message rendering window. Reopen the sidebar chat to return to the selected source branch. Search indexes the selected source branch only.
- Markdown exports often omit model metadata and alternate branches. Those fields are shown only when saved; installing the live-page extensions does not reconstruct omitted offline data. Extension-only send timers or request records are not invented.

## Organization and controls

- Add, rename, or remove **categories**. Removing a category preserves its chats.
- Drag a chat onto a category heading to move it. Drag it onto another chat to place it before that chat; only the destination group switches to manual order. Manual order is stored within each displayed group. Dragging across a category sets the destination category.
- Pin chats; customize their display titles; manually correct Chat/Work/Codex classification, or return a chat to Automatic classification. Editing a title or category leaves automatic classification enabled.
- Sort by newest, oldest, recent update, A–Z, or manual order. Newest/oldest use original creation time when available, otherwise source timestamps.
- Group by categories, disk folders, or chat type; show a flat list; collapse groups; hide all project chats using the Projects checkbox.
- Dark, pure black, light, or custom background/sidebar/text/accent colors. Adjust text size, reading width, and page size.
- Optional remembered reading positions; 60-second incremental file checks; optional timestamps.
- **Ctrl+K** searches the archive. **Ctrl+F** searches the selected conversation. Search matches finish loading the saved message, expand the relevant section, highlight the matching text, and scroll it into view. Enter / Shift+Enter and the up/down buttons move through literal matches in the selected conversation.
- Export/import your organization and appearance settings through Settings. This backup includes local source-folder paths; keep it with your own archive.

## Search: fast text now, local meaning search optionally

**Keywords:** SQLite FTS5 with BM25 ranking, English stemming, Unicode tokenization, and prefix matching. Searches message contents, titles, and IDs. A query first tries all words, then broadens to partial matches when few results exist.

**Smart text:** the same fast index plus a small transparent set of related-word groups (for example `forecast/weather/rain` and `cognition/intelligence/IQ`). It is useful immediately, but **is not a neural semantic model**.

**Semantic / Hybrid semantic:** optional local multilingual sentence embeddings and normalized dot-product similarity. Hybrid merges text and semantic ranks using reciprocal-rank fusion. A* is a pathfinding algorithm and is not used for archive retrieval.

Select **Semantic** or **Hybrid semantic** in search, or **Settings → Enable / rebuild semantic search**. The viewer uses its bundled Python and pip tool to install a private CPU engine and download the multilingual model automatically. No separate Python installation, command entry, or restart is required. The first setup needs internet, can take several minutes, and can use over 1 GB of disk. **Conversation files are never uploaded.** Setup progress and indexing counts appear in Settings. If interrupted, select semantic again to retry; downloads use a local cache.

After setup, the model is loaded with `local_files_only=True` and searching works offline. Text search remains usable during setup/indexing. Changing exports invalidates the semantic index until rebuilt. Semantic retrieval scans the local vectors; latency and memory grow with archive size. A similarity score does not prove equivalence.

`SETUP-SEMANTIC.bat` remains an optional way to prepare the model before opening the viewer. It uses the bundled runtime rather than installing Python system-wide. On macOS/Linux, the same setup helper uses the Python running the viewer and installs packages in the app folder.

**Exact phrase:** literal, case-insensitive phrases with Unicode normalization and word boundaries. **Exact + typos:** exact hits rank first, followed by conservative spelling corrections, adjacent character swaps, missing characters, and final-word completion. Candidate words come from the existing FTS index, then message text is checked in order. Each result identifies an exact, close, or completion match; this mode requires no model download or reindex.

## Files and privacy

All app assets are local. The server binds to `127.0.0.1` on a free port, requires its random launch token, and rejects cross-origin writes. Ordinary message HTML and attachments cannot run scripts. Saved HTML app widgets run in a separate sandbox that cannot access the viewer or make network requests. External conversation/document links open only when you click them.

Your local cache is `.viewer-data/archive.sqlite3`, alongside the app. It stores parsed messages, search indexes, organization, and appearance. Keep this folder to preserve your cache and settings. Do not share the folder or export-settings file publicly if your conversations are private. The packaged download contains **no copies of your uploaded conversations**.

## Troubleshooting

- **No chats appear:** select the actual export output folder, not the extension source folder. The supplied exporter package itself is software, not your conversation archive.
- **Folder browser fails:** paste the folder path directly. Windows uses its native folder dialog through built-in PowerShell.
- **Original link unavailable:** a Markdown file with no conversation URL and no resolvable ID cannot supply a legitimate original link.
- **New files missing:** click Scan & index or enable periodic checks. Look at Discovery notes for permissions, parse errors, or traversal limits.
- **Missing attachment:** its file was not saved or its referenced path no longer matches. No binary is redownloaded automatically.
- **Disconnected:** restart the launcher. A new session URL is printed.
- **Reset cache:** stop the viewer, move `.viewer-data` aside, and reopen. This affects the viewer cache/settings, not source exports.

## Changes in v1.0.13

- Saved line, area, bar and scatter chart widgets render locally with labels, units, legends, data and source folds. Hover or use arrow keys to inspect values; line-chart hover cards show all active series for the selected point. Unknown chart types retain a readable source fallback.
- Self-contained saved HTML apps run in an isolated frame with network access disabled. The frame grows to fit the content. Local sliders, selectors, SVG charts and saved scripts work; apps requiring remote libraries, server APIs or missing export files may remain incomplete.
- Code folds are closed by default. Expand them to read, wrap or copy code. Unknown code languages are inferred, and shell-wrapped Python highlights both the shell wrapper and Python body. Large blocks retain readable plain text rather than blocking the reader.
- Fixed the first-column wrapping rule that caused overlapping fitted tables. The repaired wrapping also applies in the expanded table dialog.
- In-chat Find uses literal ordered occurrences, including user prompts. It loads complete long messages before highlighting, opens collapsed sections and follows layout changes while the message settles. User scrolling releases that temporary anchor.
- Archive results are grouped by conversation with highlighted snippets, sender labels, type/category filters, relevance/recent/A-Z ordering and access to additional message matches. Filters apply before ranking limits. Next/previous navigation opens matches across chats; Back to archive results keeps the query and result list.
- Organization is layered: the selected Chat/Work/Codex filter, pins and group structure remain in place while each group sorts its own chats. Move group headings with drag or up/down buttons. The group sort button selects an independent order, or follows the sidebar default. Preferences persist and are included in organization backups.
- Chat reordering and category renaming save their changes in a single batch to avoid a request for every chat.
- Existing indexes receive code-presentation repairs when read. No full content reindex is required for these rendering and search fixes.

## Classification and account metadata

Project membership, conversation titles and prompt/code content do not determine the product type. The viewer checks saved product fields, model receipts across saved branches, and native Codex session records. It never uses a private list of account-specific conversation IDs.

If an export omits the account plan, the viewer cannot prove whether Luna was served to a free account. Use the conversation menu to set Chat when needed; choose Automatic to return to saved metadata. Manual corrections are kept in the local viewer settings.

## Validation

The release was checked with 114 automated backend tests and JavaScript checks for widget extraction, layered sorting, type filtering and syntax colouring. Windows Edge browser checks exercised the reported charts and saved interactive app, hover details, exact highlights, search navigation, the overlapping four-column table in both views, folded Python/shell code, category ordering and per-group sorting. The bundled Windows runtime was used for the backend checks.

The general release includes neutral preview data only in its documentation image. Personal exports, private indexes, account-specific ground-truth scripts/lists, test fixtures and test helpers are excluded.

Optional semantic engine/model installation was not repeated for this update. Exact, typo-tolerant and ordinary text search require no downloads.

The portable ZIP contains the application, local web assets, bundled Python/runtime libraries and their licenses. Conversation files, personal indexes/settings, account ground-truth helpers, development scripts and test fixtures are excluded.

## Rollback

Stop the updated viewer, restore the previous app files, keep .viewer-data, then run START-VIEWER.bat. Source exports are never altered. Move .viewer-data aside only if you intentionally want a fresh local index and settings.

## Licenses

Third-party licenses accompany the bundled CPython, Microsoft runtime, pip, Marked, KaTeX, Highlight.js and branch helper components. Keep their license files when redistributing this portable application.
