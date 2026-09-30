# Offline Chat Viewer · v1.0.11

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

When updating, close the old viewer console, replace the app files, **keep `.viewer-data`**, and reopen START-VIEWER.bat. Your existing index and organization remain available; rebuilding the cache is unnecessary. If loading still stalls, run **CHECK-VIEWER.bat** while the viewer is open and attach **VIEWER-DIAGNOSTICS.json**. The report includes response lengths, received bytes, and transfer timings, with no conversation text, titles, folder paths, or session tokens.

## Discovery and formats

- Reads your English Autopilot export: individual `.md` / `.json` conversations, `conversation-index.json`, and `portable-state*.json` metadata.
- Also reads standard ChatGPT `conversations.json` arrays, simple `{title, messages:[...]}` JSON, and explicit-role Codex `.jsonl` session records.
- **MD and JSON copies merge by conversation ID. JSON is preferred**, preserving its selected branch and message metadata. Additional JSON branches are available under **Branches**.
- `conversation-index.json` enriches matching files with original links, project names, chat kind, and calendar dates. Manifest entries with an existing saved file appear before full-text indexing finishes and can be opened immediately. Entries without files are counted separately in Discovery notes.
- **Pause discovery / Stop current scan** cancels the background worker; an interrupted transaction rolls back safely. Cached chats remain available. A new folder request cancels the previous scan and starts the new scope; it is never silently ignored. Pause persists across restarts.
- Export folders shows the scan boundary, current folder/file, files discovered/checked, changed chats, and unchanged files.
- A separate background process and a file-path queue capped at the discovery limit let discovery and indexing overlap without sharing the foreground reader’s Python interpreter. A persistent per-file checkpoint skips unchanged chats and unrelated documents on later scans, including after restart.
- Scans additional folders when you choose them; previously indexed conversations remain cached. Original exports are never rewritten or deleted.
- Original Work/Codex/Chat labels use saved product metadata. Saved Work model markers can supply an inference, identified in the chat tooltip. Exporter labels normal-chat/project-chat normalize to Chat; project membership is independent of product type. Existing cached receipts and bounded source headers update types automatically. Manual overrides remain available and take precedence. Titles and code blocks are not treated as evidence of chat type.
- Tool output, analysis channels, and reasoning-summary objects are hidden initially. **Tool details** reveals them. The original content stays in the index and source file.
- Symlinks, Windows system folders, hidden caches, dependencies, model files, and the viewer index are skipped. Automatic upward traversal stops before a drive/filesystem root. Downward traversal is limited to 24 directory levels / 25,000 directories / 100,000 candidate files; any limit appears in Discovery notes.
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
- Drag a chat onto a category heading to move it. Drag it onto another chat to place it before that chat; the list switches to manual order. Manual order is stored within each displayed group. Dragging across a category sets the destination category.
- Pin chats; customize their display titles; manually correct Chat/Work/Codex classification.
- Sort by newest, oldest, recent update, A–Z, or manual order. Newest/oldest use original creation time when available, otherwise source timestamps.
- Group by categories, disk folders, or chat type; show a flat list; collapse groups; hide all project chats using the Projects checkbox.
- Dark, pure black, light, or custom background/sidebar/text/accent colors. Adjust text size, reading width, and page size.
- Optional remembered reading positions; 60-second incremental file checks; optional timestamps.
- **Ctrl+K** searches the archive. **Ctrl+F** searches the selected conversation. Search matches jump directly to the saved message.
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

All app assets are local. The server binds to `127.0.0.1` on a free port, requires its random launch token, rejects cross-origin writes, and does not execute HTML/scripts embedded in messages or attachments. External conversation/document links open only when you click them.

Your local cache is `.viewer-data/archive.sqlite3`, alongside the app. It stores parsed messages, search indexes, organization, and appearance. Keep this folder to preserve your cache and settings. Do not share the folder or export-settings file publicly if your conversations are private. The packaged download contains **no copies of your uploaded conversations**.

## Troubleshooting

- **No chats appear:** select the actual export output folder, not the extension source folder. The supplied exporter package itself is software, not your conversation archive.
- **Folder browser fails:** paste the folder path directly. Windows uses its native folder dialog through built-in PowerShell.
- **Original link unavailable:** a Markdown file with no conversation URL and no resolvable ID cannot supply a legitimate original link.
- **New files missing:** click Scan & index or enable periodic checks. Look at Discovery notes for permissions, parse errors, or traversal limits.
- **Missing attachment:** its file was not saved or its referenced path no longer matches. No binary is redownloaded automatically.
- **Disconnected:** restart the launcher. A new session URL is printed.
- **Reset cache:** stop the viewer, move `.viewer-data` aside, and reopen. This affects the viewer cache/settings, not source exports.

## Validation and source

`python -m unittest discover -s tests -v` runs parser, branch, duplicate, discovery, search, paging, organization, attachment-boundary, and HTTP/session tests. All 49 automated tests passed, including bounded catalog responses, compressed UTF-8 response lengths, growing catalogs, and diagnostic checks. The delivered version was also exercised in Chromium using a neutral long-conversation fixture, plus parsed against your supplied MD/JSON/index/portable-state files. Optional model download/inference and native Windows launching were not executed in this Linux build environment.

Third-party licenses accompany the Marked, KaTeX, and bundled CPython distributions. Sources: [SQLite FTS5](https://www.sqlite.org/fts5.html), [Sentence Transformers](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html), [KaTeX](https://katex.org/docs/autorender), [Python Windows embedding](https://docs.python.org/3/using/windows.html#the-embeddable-package).

## Reference extensions

Model field priority and receipt presentation were checked against [Lex-au/chatgpt-receipts](https://github.com/Lex-au/chatgpt-receipts). Branch traversal was adapted from the supplied ChatGPT Version Arrows archive; its MIT license is included. The offline reader uses local saved metadata/graphs and does not install or run either live ChatGPT extension.

## v1.0.1 startup / discovery fix

- JavaScript, CSS, HTML, and fonts are served with explicit application MIME types; Windows file associations cannot prevent the reader scripts from executing.
- The folder controls initialize before index requests and optional Markdown/math libraries. A delayed index response does not prevent choosing a folder. Failed startup requests time out and retry, while controls remain usable.
- The scanner indexes files as they are found, prioritizes the chosen folder, reports live paths/counters, yields time to foreground requests, and supports cancelling/replacing scans.
- SQLite WAL is configured once, connections are closed promptly, and state reads remain responsive during index writes. The sidebar is resent/rebuilt only when its contents change.
- A held-back index response plus delayed Markdown loader was tested in Chromium: Choose folder remained clickable (92 ms in the test). The interface also passed its existing reading, search, branch, model badge, theme, and drag-and-drop checks. Native Windows execution is still not available in this Linux test environment.

### Updating from v1.0.0 / v1.0.1

Close the old viewer console first. Replace the contents of its `offline-chat-viewer` folder with this version's contents; keep `.viewer-data` to preserve the indexed archive, categories, and preferences. Reopen START-VIEWER.bat. Alternatively extract to a new folder and copy `.viewer-data` from the old app folder. In Export folders choose your actual exporter output folder for the most focused scan.

Technical references: [Python MIME registry behavior](https://docs.python.org/3.13/library/mimetypes.html), [Browser script MIME requirements](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options).


## v1.0.2 selected-chat priority / archive coverage

- Selected messages do not wait for the archive scan, search indexing, Markdown, or KaTeX. Plain text appears first if the optional renderers are still loading, then upgrades in place.
- Background indexing runs in a separate spawned process. Message requests signal it to yield. A single foreground reader opens available manifest files before their turn in the search index; only one reader task runs at a time.
- The sidebar creates its first five chat rows immediately and continues in batches of five. This renders titles only; it does not load the contents of every chat. Only the selected conversation fetches a message page.
- The latest 20 messages render first in batches of five, followed by the remainder of the latest 100-message page. Scrolling loads further pages with a 300-message limit. Switching chats cancels the obsolete client request and render queue.
- The five most recently viewed conversations retain their rendered page and scroll position for fast returns. This is an in-session, bounded cache; a page-size, details, branch, or source-fingerprint change gets a fresh page.
- A reader error hides the end-of-conversation card and presents **Retry opening chat** instead of leaving an empty chat that looks finished.
- Export folders reports **manifest entries / available files / indexed chats** independently, plus missing-file examples and discovery notes. A count during scanning is not a completed inventory. Original filenames/paths from `conversation-index.json` locate saved files; titles and IDs can be searched before full content indexing finishes.
- Generic folders named `web`, `tests`, `models`, or `runtime` are scanned when they belong to the export tree. The viewer’s own assets are excluded by exact path.
- Mapping node IDs use a direct lookup rather than a repeated whole-mapping search. An indexed row map avoids rescanning the whole full-text table whenever a chat is updated; existing caches migrate automatically.

Validation used a synthetic 713-chat archive with 120 messages per chat. All 713 titles appeared while only 2 chats were fully indexed; opening the final unindexed conversation took 0.097 seconds. The scan then completed all 713 with no errors after pause/resume. These timings describe the test machine and fixture, not a guarantee for other disks or export sizes.

Chromium additionally verified a 713-row sidebar, five-row initial batches, messages appearing while Markdown/math scripts were withheld, cancellation of a deliberately stalled old chat request, returning to a cached chat without another message request, eventual rich rendering, and retry after a deliberate read failure. The existing paging, search, branches, model metadata, attachments, appearance, organization, and startup checks also passed. Native Windows execution and optional neural inference remain untested in this Linux environment.


## v1.0.3 Markdown discovery / startup fix

- `/api/state` serves an in-memory snapshot of titles, settings, and progress. It never opens SQLite or waits for a database read. Cached archive loading happens separately; newly discovered files can appear while that finishes.
- Markdown files are announced from their first 8 KiB as soon as discovered. The file-path queue no longer stops discovery after 32 pending files, so large chats do not hold the remainder of the title list behind their full-text indexing.
- The selected chat reads its saved source on a dedicated foreground thread, including before the search index contains it. Cached conversation data remains a fallback when an original source was moved or is unavailable.
- The scan subprocess uses the database schema already initialized by the launcher; it does not repeat WAL/schema initialization while the reader is starting.
- The browser opens on a separate thread after the local server is ready to run. Native browser-launch delays cannot hold up the server loop.
- Scan start/stop settings persist in the background, so the folder action does not wait on an indexing write transaction.
- The scanner subprocess exits if its launcher is forcibly closed. The selected-chat reader runs inside the server, avoiding a second executable launch or process-IPC dependency. The sidebar badge identifies version 1.0.4; `/api/health` is a small database-free status endpoint.

Validation used the actual supplied Markdown archive: **702 files, 492,972,884 bytes, all 702 indexed, zero parse errors**. In a cold Chromium run all 702 titles appeared in 417 ms with only 3 chats indexed. An unindexed chat displayed its first messages in 160 ms, with no browser errors. A separate full scan kept status/message requests below 0.11 seconds. Timings describe this Linux test machine; the exact Windows timeout was not reproduced here.

All 39 regression tests passed, including status with database methods deliberately unavailable, direct reading of an unindexed Markdown file, and worker startup without schema access. Existing Chromium checks for messages, math, tables, attachments, branches, model metadata, paging, search, categories, drag/drop, appearance, delayed startup, cancellation, and cached returns also passed. The supplied conversations are not included in the viewer download.


### v1.0.3 reading and formatting

- Selected-chat parsing now uses one dedicated thread in the server instead of launching another Python executable. Background indexing remains in its separate process. The exact “Preserve JSON Dialogue Format” file from the reported stuck chat contains 10 visible messages; Chromium displayed its first messages in 36 ms while the rest of the archive was indexing.
- Math placeholders render directly through local KaTeX rather than relying on a second auto-render script. Display equations, inline formulas, and long equations receive proper spacing and horizontal overflow. Failed renderer downloads can retry when opening another chat; the initial text stays usable.
- Saved citation markers render as compact **Sources** chips, preserving raw IDs in the tooltip and original message copy. When no saved source URL is available, the chip explains that instead of inventing one. The original chat remains available through Continue original chat.
- Reading uses tighter 1.62 line spacing, semibold headings/emphasis, consistent paragraph/list spacing, cleaner table borders, and clearer code/math blocks.
- A saved chat/message link restores once its file is discovered, including when the first status response contains no titles.

The actual messages shown in the formatting screenshots were checked in Chromium: citation chips replaced raw internal markers and the four display equations rendered with KaTeX. No raw citation IDs or raw equation commands remained in the reading text. Copying a message still preserves its original exported text.


## v1.0.4 startup response / sidebar batches

The Windows diagnostic showed the matching v1.0.3 process, 702 cached chats, and a status request that returned HTTP 200 headers but timed out while receiving its body. Health requests before and after it succeeded.

- The startup status response contains at most five titles. The remembered or linked chat is first when available.
- Remaining titles download independently, at most 25 per response with an approximately 16 KiB metadata budget. A timed-out batch retries with five. Discovery can continue during this queue.
- Status polls omit large reading-position settings and unchanged sidebar data. Cached titles do not require full-text reindexing.
- Larger JSON and text responses use local gzip compression when supported. Small response writes disable TCP delayed-packet batching.
- Searches can open a chat before its sidebar metadata arrives. A slow metadata lookup cannot override a later selection.
- CHECK-VIEWER.bat now reports content lengths, received bytes, and server transfer progress. It omits chat content and session tokens.

All 49 automated tests passed. Chromium tested the real 702-chat cache against a deliberate HTTP-200 response-body stall: the initial state was 3,005 bytes, the saved chat rendered before the blocked sidebar batch completed, the batch retried with five, and all 702 titles eventually appeared without duplicates. Reading, search, paging, formatting, model/branch metadata, drag/drop, appearance, saved-thread restoration, and stale-request cancellation also passed. This reproduces the reported transfer stage in the Linux test environment; the underlying Windows transport cause has not been established.


## v1.0.5 selected-chat downloads and rich reader

The reported error identified a stalled `/api/messages` response body. The reader now separates message downloads from Markdown formatting and avoids transferring the full 100-message page at once.

- Initial requests ask for five messages. Subsequent requests ask for at most ten while filling the initial page, or twenty while scrolling. A JSON byte budget further reduces each response; omitted rows remain available in the next page.
- A message-body timeout retries with an 8 KiB budget. That conversation keeps the smaller budget for subsequent history requests. Each request has its own timeout controller; retrying does not poison the selected-chat cancellation signal. Switching chats cancels stale requests.
- Long messages show their saved prefix immediately and fetch the rest in bounded fragments. Unicode and JSON escapes are counted without dropping content. User messages have a Load complete message control; assistant messages near the viewport load and format automatically.
- Unchanged indexed files use SQLite rather than reparsing the whole export on each page. New or changed files retain foreground reading before indexing finishes.
- Markdown parsing runs in a dedicated browser worker. Only messages near the viewport receive rich formatting. Bundled Markdown and math scripts download in small chunks; no external renderer or favicon requests are needed. Math arriving during a history request still typesets.
- Messages, headings, code blocks, and saved HTML details have collapse/expand controls. Collapse all / Expand all affect loaded content. Fold choices survive in-session rerenders and cached returns. Code headers show the saved language and offer Copy.
- Tables use readable column widths, intact time labels, sticky headers, horizontal scrolling, collapse and Copy controls. Expand opens a wide table dialog with text wrapping and comfortable/compact density. Closing it restores the original table and scroll position.
- Explicit saved reference-to-URL metadata and Markdown reference definitions produce clickable source chips with a local icon or domain initial. A +N chip opens the remaining sources. File references and citations without a saved URL show their saved IDs in a separate panel; URLs are never guessed. Raw original text remains available through Copy message.

Validation: **53 automated tests passed**, covering bounded downloads, complete Unicode fragment reconstruction, source URL associations, indexed-read reuse, discovery, search, branches, diagnostics, and HTTP behavior. Chromium tested the actual previously stalled conversation (110 visible messages) against a deliberately stalled HTTP-200 message body: it recovered using smaller responses and displayed 100 messages while folder controls stayed usable. All 702 cached titles remained available. Separate checks covered wide tables, folding and persistence, source links/icons, long messages, delayed math assets, stale-request cancellation, cached returns, search, organization, appearance, model/branch controls, and the equations shown in the supplied screenshots. These checks ran on Linux; native Windows execution and its underlying transport cause remain unverified.


## v1.0.6 code/output blocks and exported hyperlinks

- Saved JSON `code` and `execution_output` message types retain their language and preformatted presentation. A complete valid unfenced Python program is recognized in Markdown exports and older cached messages; normal prose continues through Markdown. Python comments no longer become headings, and indentation/newlines remain intact. No cache rebuild is needed.
- Linked-message jumps prioritize the requested message for formatting. Code blocks use bundled offline Highlight.js 11.11.1, with language headers, syntax colours, exact-text Copy, folding, and horizontal scrolling. Highlighting runs in the existing worker. STDOUT/STDERR uses a separate monospaced output panel, preserving literal escape sequences and indentation. Original message copy remains unchanged.
- Switching Tool details now fetches the correct page instead of caching the visible-only page under the new details setting.
- Exported `url` markers become labelled links when their explicit URL or saved source metadata is available. If an MD export saves only a label and reference ID, the label opens the saved-reference panel; the target is not fabricated. Repeated source IDs use the exact message metadata, preventing a later link from inheriting an earlier message's URL.

Validation: 58 automated tests passed. Chromium verified unfenced Python, comments remaining code, exact copied text, syntax colouring, separate output, folding, literal escaped newlines, normal Markdown, fenced-code highlighting, exported URL labels/targets, missing-target references, and Tool details. Existing checks for wide tables, sources, delayed math, long messages, stalled-download recovery, active-chat priority, cached returns, search, appearance and branches also passed. Checks use neutral rendering fixtures and the supplied cached archive; private conversations are not packaged.

Third-party syntax renderer: [Highlight.js](https://github.com/highlightjs/highlight.js), [official prebuilt assets](https://github.com/highlightjs/cdn-release/tree/11.11.1), BSD-3-Clause. Its license is included in `web/vendor/highlight-LICENSE.txt`.


## v1.0.7 targeted rendering repair

Python scripts containing Markdown fences inside string literals now retain code presentation, indentation, highlighting and folding, including older cached messages without rebuilding the index. Previously any occurrence of fence characters bypassed Python detection. Actual fenced Markdown and prose remain Markdown.

This repair has a regression test covering a multiline TSV string, embedded fence characters, and an older cached row. The previously supplied full affected export was unavailable during this pass; this release does not claim that every screenshot block has been reproduced.

Validation for v1.0.7: all 59 automated tests passed, including local HTTP responsiveness and regression coverage. The actual rendering worker also passed code, indentation, exact-text, HTML escaping, highlighting, table and link checks under Node. No fresh full-browser or native Windows run was performed for this small backend change. ZIP member checks and saved-download verification accompany this release.


## v1.0.8 tables during loading and code editor panels

Long-message prefixes are formatted immediately; fetching the remaining body runs afterward. Tables, emphasis, links, and code controls stay usable while the rest loads, and a failed fragment leaves a visible retry button. Completing the message preserves code/table scroll positions. Copy on incomplete code is labelled Copy visible.

Shell heredoc exports beginning with bash/sh/zsh -lc or -c retain code semantics even though the shell wrapper is not valid Python. Code panels now have line numbers, a shared scroll area, syntax highlighting, wrapping, folding, and exact-text copying. The displayed version badge has also been corrected.

Validation: 60 automated tests passed. Chromium verified a 350-row weather table while fragment delivery was intentionally held, all rows after release, table collapse/expansion, a 1,264-line shell-wrapped Python script, highlighting, line numbers, wrapping, folding, and exact clipboard contents. These are neutral fixtures reproducing the supplied screenshot shapes; private export data is excluded from the package.

Browser checks also verified that failed fragments retain rendered tables with a working retry, and table scroll positions survive completion. See `docs/table-during-loading.png` and `docs/code-output.png`.


## v1.0.9 shell pipelines and JSON tool calls

Plain bash/sh/zsh -lc/-c commands now receive the same code panels as heredoc scripts. Complete unfenced JSON objects and arrays are recognized in exports and older cached rows. JSON displays with indentation and readable Unicode; a Raw/Formatted toggle exposes the original export, and Copy always preserves that original text. Numeric tokens are retained verbatim to avoid rounding large integers during display formatting. No index rebuild is needed.

Validation: 62 automated tests passed. Chromium checked shell pipelines, decoded Unicode, nested JSON indentation, exact large integers, Raw/Formatted switching, matching line numbers, collapse, highlighting, and original clipboard text. The long weather table, delayed fragment, retry, table scroll preservation, and previous code controls also passed. Neutral fixtures reproduce the screenshot cases. See `docs/json-code.png`.

## v1.0.10 rendering, phrase search, and automatic semantic setup

Tables default to fit the reading width through six columns, with Wide and Compact controls that survive message completion and reopening. Number/index columns stay narrow. Saved filenames appear in file-reference chips; actual saved URLs remain clickable. Missing filename/URL associations cannot be reconstructed from a reference ID alone. Incomplete explicit Python function/class exports render in code panels while retaining their exact saved text.

Math loads directly from the bundled asset with the existing fragment fallback and an actionable retry after a failed load. Long text-only arrow chains stack vertically. Heading sizes and spacing are more compact. Exact + typos search works immediately. Semantic setup now uses portable dependencies and reports progress inside the viewer; no separately installed Python or restart is required. The embedded runtime path includes the viewer folder so helper imports work after extraction. The C++ runtime DLLs are included for clean Windows machines.

Validation: 79 backend regression tests; Chromium checks progressive 350-row tables, code controls, formulas and retry, file-chip labels/links, fit/compact persistence, incomplete Python, and exact/typo/completion searches. The official CPU and sentence-transformers wheels resolved for Windows x64 Python 3.13. Native Windows execution is not available in the build environment, so an actual Windows model-install run was not tested here.

## v1.0.11 rendering recovery, chat types, and dark dropdowns

Markdown is loaded directly from the bundled asset before its bounded fragment fallback. Tables, headings and code controls no longer wait for syntax colouring. Colouring upgrades code afterward while preserving folding, wrapping and exact copying. Renderer and formula failures retry automatically; the existing table layout and controls are retained. Vendor assets are cached locally with versioned URLs.

Chat/Work/Codex use consistent canonical labels in cached, manifest and fully loaded entries. Existing cached Work receipts and bounded source headers recover type evidence in the background without rebuilding messages or changing organization. Work model markers are labelled as inference; project membership stays separate. Empty filtered views identify their filter instead of incorrectly claiming that all files are still indexing.

Native select options explicitly inherit readable theme text and panel colours, including the black theme. Validation: 88 backend tests and worker checks passed. Chromium verified automatic parser/worker recovery, readable tables and code controls while the highlighter was stalled or unavailable, exact copying, exclusive type filters, and dropdown contrast in black/dark/light themes. In the local stalled-highlighter fixture, basic formatting appeared in 117 ms; this is a test-machine measurement, not a Windows timing guarantee. Existing progressive table, code, formula, source-link and phrase-search checks also passed. Native Windows popup rendering has not been executed here.
