# Offline Chat Viewer · v1.1.14

A local ChatGPT-style reader for your Markdown and JSON exports. The standard viewer has no package-install step, cloud service, subscription, or CDN dependency. Windows x64 Python is included in the download.

## Latest Windows release

- **Download:** [Offline-Chat-Viewer-v1.1.14-Windows.zip](https://github.com/kitomisaitichi-design/chatgpt-viewer/releases/download/v1.1.14/Offline-Chat-Viewer-v1.1.14-Windows.zip)
- **SHA-256:** [Release checksum](https://github.com/kitomisaitichi-design/chatgpt-viewer/releases/download/v1.1.14/Offline-Chat-Viewer-v1.1.14-Windows.zip.sha256.txt)

## What the viewer does

Read ChatGPT Exporter folders, official ChatGPT exports and explicit-role Codex sessions locally. Browse saved branches, models, citations, formulas, tables, code, charts and self-contained HTML widgets. Search messages across chats or find a phrase within a chat. Organize your archive with independent type filters, projects, folders, pins, manual order, aliases, colours, sticky chats and reversible Trash. Normal reading and reversible Trash keep your exports intact. The optional reviewed deletion queue can remove a remote ChatGPT conversation and clean up its verified, unshared local Library copies.

The standard reader and local backups work offline. An optional semantic search engine downloads once; Google Drive delivery is optional. Windows x64 Python and rendering assets are bundled. Your personal archive, account-specific classification corrections, Google credentials and test fixtures are excluded from the application release.

## Background connection and remote status · v1.1.14

- A small dot and green **Connected** text in the status bar report a fresh, account-matched browser heartbeat. Disconnected and retry states remain visible. **Reconnect** resets the connection budget: one initial attempt and at most two retries, then automatic attempts stop until you reconnect manually. This budget persists across worker/page restarts. Shared ChatGPT rate-limit cooldown is separate and remains authoritative.
- The upgraded optional exporter 2.4.12 adapter wakes an inactive worker page within about 30 seconds when its dashboard is closed and authorized local work is waiting. It reuses the remembered folder grant, signed-in ChatGPT browser session, existing exclusive dashboard lock and Engine pacing. An already-open exporter remains the owner. The browser must be running; initial adapter setup, folder permission and ChatGPT sign-in are still required. Reinstall the adapter from the queue setup, then reload the extension and ChatGPT tab once. `viewer-bridge-upgrade-v2.zip` preserves the previous adapter, manifest and service worker; the original rollback remains intact. No extra host permissions are added.
- Queue-only execution skips archive inventories and Library discovery. A deferred conversation no longer blocks ready jobs behind it. The normal exporter still completes changed transcripts; revision mismatches require review rather than deleting a newer, unreviewed revision. Pause is checked during shared cooldown waits; an already-sent request may finish. Completed command files move to private queue history, keeping the bounded active inbox usable.
- **Deleted on ChatGPT · local copy** marks verified deletion; **Unavailable on ChatGPT · local copy** marks an authenticated inaccessible lookup. Online/continue links hide in both states while local reading and attachment previews remain available. Opening an account-indexed chat queues a cached, non-destructive availability check, without archive rescans. A pre-existing 404 does not prove deletion and does not remove local Library files. Login failures, network errors, malformed responses and foreign-account receipts never become deletion markers. Status metadata stays separate from transcript content hashes.
- Native Codex metadata discovery remains asynchronous and bodies load on opening; local Codex sessions do not enter the remote ChatGPT deletion queue.

Verification: 255 backend tests (one local Windows symlink skip), five JavaScript renderer suites, 16 contract scenarios using the real exporter Engine with simulated HTTP, and isolated browser checks for connected/blocked/reconnect states, double-click protection, deleted/unavailable labels, local rendering and refresh. Authenticated deletion and background wake in a reloaded real extension have not been exercised; the browser automation cannot access Edge's internal extension reload page.

## Deletion queue, bookmarks and native Codex · v1.1.13

- Trash rows have independent selection and delete/restore icons. Selection survives filtering; **Queue delete** opens mutually exclusive local retention options. The default cleans up unshared local Library copies after verified remote deletion; **Preserve local copy** keeps local files. Original chat JSON/Markdown and recovery backups are retained in either mode.
- Adding jobs never executes them. Review the exact pending set, then **Run**. A durable SQLite queue deduplicates by exporter account and conversation ID, snapshots linked Markdown/source/available attachments before remote work, and supports pause/stop, per-chat progress, checkmarks and restrained animation. Manual scrolling disables automatic progress following. Refresh retains jobs; restarting the viewer pauses unfinished work.
- Remote execution requires the optional, narrowly versioned **ChatGPT Exporter 2.4.12** adapter. In the queue's **Connect exporter bridge**, choose the unpacked extension folder and install. Reload the extension and its ChatGPT tab, open its dashboard and reconnect the same export folder. Installation backs up all four modified exporter files in `viewer-bridge-rollback.zip`; restore those files and remove `viewer-delete-adapter.mjs` to undo it. Other exporter versions are refused without modifications.
- The adapter enters the exporter's existing exclusive dashboard lock and Engine scheduler. It serializes requests, shares adaptive pacing/Retry-After and account scope, verifies the saved revision again before mutation, and verifies the remote result before acknowledging completion. Disconnected jobs remain queued. Expiring viewer control leases prevent old commands from running after a crash or unavailable folder. Verified deletion tombstones are separate from content hashes and survive exporter resume/index import. No competing HTTP executor runs in the viewer.
- **Remote ChatGPT Library deletion is unsupported.** The retention choice concerns local Library files. Shared files remain; removed unshared files also have same-volume recovery and SHA-256-checked backups under `.viewer-queue/recovery` and the viewer data directory's `deletion-recovery`. Recovery material is private and excluded from application releases. Authenticated remote deletion has not been exercised against a real account; contract tests simulate HTTP while using the actual exporter gate/pacing.
- A separate searchable **Bookmarks** panel opens from the sidebar or thread toolbar, with open/unbookmark and a current-chat toggle. Pins keep their existing ordering behavior. Bookmark/type metadata participates in shared cross-version preferences and settings backup/restore.
- **Export folders → Detect native Codex chats** discovers validated local session metadata under `CODEX_HOME` and the current Windows profile's `.codex/sessions` / `archived_sessions`. Discovery runs asynchronously; bodies load on opening. State database titles require an exact session-path match. An incomplete final JSONL row is tolerated; malformed interior rows are reported. Explicitly linked local images/documents reuse the normal viewers and authorization checks. Native sessions use reversible local Trash, with no remote ChatGPT deletion action.
- **Mark as Codex** and **Use automatic chat type** are durable organization fields, independent of folder, pins and ordering. Local source names and IDs are preserved. Explicit links into Trash can be refreshed without losing the opened chat.

Verification: 250 backend tests (one Windows symlink skip), five renderer/catalog JavaScript suites, eight exporter adapter contract scenarios, and isolated browser checks for empty selection, filtering, double submission, async backup, pause/refresh, bookmark search/removal and type persistence. No real account deletion was run.

## Linked attachment previews and controls · v1.1.12

- Image navigation uses full-height 64 px translucent side strips with centered SVG chevrons on hover/focus. Unavailable directions hide; arrow keys, fitted swipe, wheel zoom and zoomed panning remain available.
- A consistent SVG thread toolbar adds a light-bulb light/dark toggle, a separate theme palette and navy **Midnight**. The previous dark theme, chosen theme and attachment-pane width are retained in the existing shared cross-version preferences.
- **Copy text** copies the complete explicitly linked original Markdown, independently of loaded message pages. With JSON-only exports or an alternate saved branch, it generates Markdown from that branch and identifies the fallback. Conflicting Markdown originals are not guessed.
- Compact prompt-linked document cards show filename, type, size and availability. Open a card, the thread Files button or an associated Library document in a resizable right pane. Expand, close, **Go to prompt**, chronological previous/next, search and zoom remain inside the viewer. Narrow windows use a full-width pane. There is no additional download button; **Open original** uses the existing original-file route.
- Markdown preview/raw views reuse the existing LaTeX and table renderer. Text/code is selectable. PDF pages render on demand with selectable text and cross-page search. Word DOCX displays tables and embedded images. Excel XLSX/XLS and CSV/TSV offer worksheet selection and 200-row pages. Previews are read-only; Office layout is approximate and spreadsheet previews show saved values, without recalculating formulas or preserving every workbook formatting feature.
- PDF.js 6.4.299, docx-preview 0.4.1, JSZip 3.10.2 and SheetJS CE 0.20.3 are bundled in portable releases and lazy-loaded locally. Source builds run `python scripts/vendor-documents.py` to download pinned, SHA-256-verified upstream assets. No runtime CDN is required. PDF/Word preserve original page colors; the surrounding controls follow the selected theme.
- Attachment APIs reuse the image resolver, source/branch revisions, cached Library and root checks. Explicit IDs/paths win; ambiguous filenames are not assigned to prompts. Unpositioned Library files appear last and are labelled. Markdown images require thread provenance or the document's own `_files`/`.assets` directory; a shared export directory alone does not establish ownership.
- Only opened documents load bytes. Preview bytes retain at most two files / 64 MiB; metadata retains eight catalogs. Navigation aborts stale fetches, releases PDF and spreadsheet workers, removes Word frames and guards worksheet/page completions. Opening previews does not request archive rescans or sidebar rebuilds.
- Limits: 64 MiB per preview, 256 MiB expanded Office ZIP data, 20,000 ZIP members, first 1 MiB of text displayed, and up to 20,000 rows / 100 columns per worksheet. Unsupported, missing, encrypted or damaged files explain the problem and retain original-file access where locally available. Document scripts, macros, external relationships and external resource loading are disabled; Word renders in an opaque sandbox with nonce-authorized bundled scripts.

## Reliable images during active exports · v1.1.11

- Repairs a real large-archive failure where the image catalog exceeded the 15-second request timeout even though the JPEG was already saved. Catalog construction now joins validated relative paths without resolving every missing attachment on disk; source-reference deduplication avoids repeated JSON serialization.
- Thumbnail and enlarged-image delivery reuse the bounded thread catalog snapshot instead of rebuilding the complete Library twice per image. Each delivered file still gets fresh root, symlink, size and raster-signature checks. Updated catalogs continue to follow source, branch and manifest revisions; new downloads can appear without reindexing chats.
- Fixes filename aliases matching the same catalog item twice and producing a false missing-image entry. Genuine ambiguous filenames remain unresolved rather than selecting an unrelated image.
- Gives cold image catalog requests the same 60-second allowance as long-chat reads. Failed requests show their actual error beside Retry; retries coalesce, and stale failures cannot alter a different chat.
- Verified the reported personal chat locally: all eight images in its affected message decoded, including IMG_0058.jpeg at 1152×1536, with enlarged viewing, wheel zoom, fitted swipe, navigation and refresh. Private files and screenshots are excluded from the portable release.

## Documents and thread images · v1.1.10

- Exported `:::writing{variant="document" ...}` (also email/essay) enclosures become titled cards with **Copy document** and **Expand document**. The existing Markdown, formula, table, code-folding and saved-citation renderers still handle the body. Code-fenced examples and malformed headers remain literal; partial messages can render before the closing marker arrives. Copy preserves the original body Markdown and LaTeX.
- Locally saved raster images appear as lazy thumbnails in their messages. Native image pointers and local Markdown/HTML images resolve through the same export roots and attachment/Library catalog. Open a thumbnail, inline image, associated Library file, or the **View all images in this chat** header button.
- The enclosed image viewer supports **mouse-wheel zoom** (100–800%), **drag to pan while zoomed**, **horizontal drag/swipe while fitted**, **←/→**, **+/−**, **0/Fit**, and **Escape**. **Go to prompt** opens the original message, including messages outside the loaded rendering window. Motion follows the system reduced-motion preference.
- Ordering follows saved message/prompt order. Repeated references share one image entry with their original prompt occurrences. Associated Library images without a saved prompt association appear last and are clearly labelled; their prompt-jump control is disabled rather than inventing an association.
- Gallery metadata is bounded and fingerprint-cached by source revision, selected branch and attachment-manifest revision. It reuses the coalesced source reader; no repeated recursive image discovery or whole-thread DOM rendering. Only the selected and next image are decoded ahead, with at most three retained image elements. Missing copies offer retry and can arrive without reindexing the conversation.
- Images stay local: remote URLs are not fetched, attachment paths remain root-bounded, and the image endpoint checks raster signatures before inline delivery. SVG/HTML and unsupported formats remain available through the existing download flow. No new dependencies or automatic changes to source exports, backups, organization or saved preferences.

## Backups while the exporter is running · v1.1.9

- Backup capture, ZIP packaging and Drive delivery run as separate background stages. The ZIP reads verified captured bytes, so rewriting `attachments/library-catalog.html` or a chat after capture cannot abort packaging.
- A file changing during capture gets two bounded attempts, then yields to an automatic retry with backoff. Other verified files are retained, the pending request survives restart, and the UI shows **Waiting for exporter** with its retry time. Cancel still stops work and preserves completed ZIPs.
- A backup is a per-file capture over an interval, rather than a transactional point-in-time snapshot of the entire exporter. Newer writes enter the next backup. A continually unstable file delays completion instead of silently producing an incomplete full ZIP.
- Captures reuse unchanged files and require additional local disk space for one captured copy. Packaging verifies SHA-256 against those copies. Original paths, linked indexes and source provenance remain intact.
- Repeated unchanged requests reuse the same ZIP bytes. Changed backups replace `Chat-Archive-Full.zip` and/or `Chat-Archive-Progress.zip` atomically; the selected two modes remain separate. Drive delivery skips unchanged verified copies. Source archives and unrelated ZIPs are never deleted.

## Exporter 2.4.10, queued updates and reliable mirroring · v1.1.8

- Reads current large exporter manifests up to 128 MiB with a bounded fingerprint cache that retains useful metadata and drops logs/job internals. Duplicate JSON copies prefer source update dates over local rewrite times.
- Continue using the complete exporter folder selected in the loader. Nested backups, content-addressed attachments and Library-only handoffs are recognized. Folder inspection reports nested export roots, and empty conversation indexes no longer hide saved Library files.
- ZIP creation completes locally before delivery starts. If Drive is unavailable, both completed ZIPs remain downloadable and delivery is saved for retry. Retry checks the saved ZIP hashes and never rescans an offline source. Changing destinations or replacing ZIPs cannot silently redirect a retry.
- Busy backup/copy requests enter a bounded, persistent queue. Repeated requests with the same delivery policy combine; local-only requests remain separate. The queue recovers after restarting or upgrading. **Cancel work & retries** cancels queued/active work and pauses delivery; **Retry saved ZIP delivery** resumes it explicitly.
- Failed delivery retries after 2 minutes, then backs off up to 6 hours. Automatic jobs still obey the selected idle and power rules. After a manual cancellation, periodic backups wait until their next interval. Local-only creation never implicitly publishes changed ZIPs.
- With automatic backups enabled, **Back up exporter updates after two quiet minutes** checks only known manifest timestamps/sizes, including nested roots. It queues a new backup once those markers settle and idle/power rules allow it. The hourly interval remains the fallback; switching this option off leaves interval-only backups. No recursive archive scan runs on every timer tick.
- Drive for desktop detection prefers an available `G:\My Drive`, populates its dedicated backup folder and preserves your custom choices. The viewer verifies local synced-folder copies; Google's desktop application performs the cloud upload. No API setup is required for this route.

## Exporter 2.4.4 and selective ZIPs · v1.1.7

- Recognizes `viewer-handoff.json` alongside the conversation index, portable state and Library index. Folder checks show the saved exporter version; selecting `json` or `markdown` detects its parent export root.
- Files & Library retains shared chat/Library source names, source presence/history, previous saved versions and chat references. Filter Chat, Library, retained references or previous versions; search original source names. Historical versions remain distinct and an older same-size file with a conflicting SHA-256 cannot substitute for the current version.
- Choose **Markdown**, **JSON / sessions**, **Images** and **Other files** independently in **Backups & Drive → Include in each ZIP**. Exporter metadata remains included. Unselected large assets are not hashed. An empty selection or metadata-only source fails with an actionable message rather than producing a misleading tiny full backup.
- Drag the sidebar edge to resize it (260–560 px, bounded by the viewport). Its width persists across versions and backups. Arrow keys adjust the focused edge; double-click resets it. Navigation, type tabs, organization and list sections have clearer spacing and subtle borders. Resizing updates width once per animation frame without rebuilding chats or resetting scroll.
- Source and Drive candidate menus populate after **Quick scan & autofill**, while existing folder choices remain authoritative. Detection prefers mounted `G:\My Drive` and correctly locates My Drive inside mirrored GoogleDrive folders. Choosing a detected Drive location fills its dedicated backup subfolder; your loader folder and traversal remain the default backup source.
- **Copy existing ZIPs to Drive** verifies each completed local ZIP against its saved SHA-256 and copies the selected full/progress slots without rescanning the source or rebuilding. It works with an offline source. Google Drive for desktop performs cloud sync and reports upload completion; this action confirms the local copy.
- Progress backups follow Exporter 2.4.4's explicit shared-file references, including files outside a chat-specific attachment folder. Backups also retain sidebar date preferences, catalog filters and read-state records when settings restoration is selected.

### ZIP layout and links

```text
OPEN-ARCHIVE.html           Offline browser of chats and file types
archive/                   Selected original files and folders
  json/                    Conversation JSON, when selected/present
  markdown/                Conversation Markdown, when selected/present
  attachments/             Original saved image and other attachment paths
  viewer-handoff.json      Exporter metadata, when present
  conversation-index.json  Exporter metadata, when present
indexes/                   Markdown, JSON, images, other files, metadata indexes
archive-index.json         Conversation-to-document/attachment cross-links
save-state.json            Original paths, kind, size, SHA-256, timestamps,
                           saved state, mode and conversation IDs
save-state.csv             The same file-state table for spreadsheet inspection
backup-manifest.json       Selected formats, recovery baseline, deleted/missing paths
viewer-settings.json       Safe appearance, reading and organization preferences
```

Extract the entire ZIP before opening `OPEN-ARCHIVE.html`. Index groups organize files by type without relocating originals; moving existing attachments would break relative links. The index links only included files. Original exporter metadata and document references may still name intentionally excluded attachments; reselect those content types for a complete linked recovery archive. JSON/session extensions inside attachment folders are **Other files**, so exported documents are not mistaken for conversations. Image selection includes raster formats and saved SVG files; SVG remains a downloadable file in the viewer.

Full ZIPs contain all selected saved content in the discovery boundary. Progress ZIPs contain changes and their selected conversation companions; the first progress ZIP includes everything selected. A later small progress ZIP can be valid. Keep the full ZIP as the base for unchanged files. File hashes change when contents change; stable slot names avoid a new daily filename. Save-state timestamps describe the source files, not proof of exporter completion. Missing remote files cannot be recreated by the viewer.

## Start on Windows / Edge

1. On Windows, right-click the downloaded ZIP → **Properties → Unblock → Apply**, if that checkbox is shown. Then **extract the entire ZIP** into a normal folder. Do not run it from inside the ZIP.
2. Double-click **START-VIEWER.bat**. It opens your default browser. Keep its console window open while reading.
3. A fresh Windows user sees a clean welcome screen. Existing users inherit their saved preferences automatically across versions. Choose **Open export folder**; a quick shallow check can suggest a saved exporter folder. Select its upward depth and start the scan. Existing installations retain their chosen source and paused/resume preference. No example conversations or test cache ship with the portable package.
4. For a precise location, click **Export folders → Browse…**, choose your exporter output folder, select `0 · only this folder` (automatically selected after Browse) or another upward depth, and click **Scan & index**.
5. Click any conversation. The selected chat has priority over indexing. Titles from the manifest can appear before their content is indexed. It displays the latest **five messages first**, then fills the reading page to your configured size (100 by default) with small background requests. Older messages load as you scroll upward.

Startup downloads at most five titles, including the remembered chat or the chat in a saved URL. Remaining titles arrive through a separate queue of up to 25 titles / about 16 KiB per response. If a batch times out, it retries with five. You can read, search, or open folder controls while this queue continues. Larger responses are compressed locally; the browser does not receive the entire catalog in one startup response.

If Edge is not your default browser, copy the launch URL printed in the console into Edge. It contains a local session token; the ordinary URL works after that first visit in the same browser. Opening the HTML file directly does not run folder discovery.

Closing the console stops the server. Settings → Stop viewer also stops it. Double-click the launcher to reopen. The bundled runtime is Windows x64; macOS/Linux can use Python 3.10+ with `python3 viewer.py` or START-VIEWER.command. Windows ARM64 can use its x64 emulation or a full Python installation.

When updating, close the old viewer console, replace the app files, **keep `.viewer-data`**, and reopen START-VIEWER.bat. Your existing index and organization remain available. Type corrections update automatically without rebuilding message contents. If loading still stalls, run **CHECK-VIEWER.bat** while the viewer is open and attach **VIEWER-DIAGNOSTICS.json**. The report includes response lengths, received bytes, and transfer timings, with no conversation text, titles, folder paths, or session tokens.

## Catalog controls · v1.1.6

- Quick sidebar search matches display/original titles, projects and categories. Full archive search still searches message contents and opens the matching turn.
- Combine read/unread, project membership, pins, untitled titles and inclusive created/updated date ranges with your current type and folder ordering. Clear filters without resetting the order.
- Date labels, created/updated/message metadata, quick rename, Open in ChatGPT, and keyboard shortcuts (`/`, `J/K`, `R`, `P`, `?`). Typing and dialogs take priority over shortcuts.
- Reading state follows your shared preferences across versions; a newer exported update becomes unread. Bulk “Mark matches read” applies to the current type/filter matches, including collapsed folders.
- Independently implemented controls inspired by [ChatGPT Triage](https://github.com/NASIRCISSISTIC/chatgpt-triage). No remote mutation queue or delete workflow is included.

## Exporter integration and rendering · v1.1.5

- Folder checks recognize the exporter root, count saved/pending conversations, and offer the correct parent when you select `json` or `markdown`.
- ZIP imports merge `conversation-index.json` and portable-state metadata, including older camelCase fields. JSON wins over duplicate Markdown; projects, dates, Work/Codex signals and exported pins are preserved. Newer existing chats and manual organization remain authoritative.
- The chat's Files button opens searchable attachments with text/image previews, copyable original paths, downloads and explicit unavailable/incomplete status. Its Library control retains manual downloaded-copy imports from v1.1.4. Downloads stream instead of loading entire files into memory.
- Long source chats build page indexes once. Markdown rendering has a bounded cache and keeps its worker warm across navigation; state/source caches are bounded. Organization restore saves one batch.
- Charts include the full numeric range, preserve sampled extremes and gaps, space numeric x-values correctly, and avoid thousands of point elements for large lines. Hover work runs once per animation frame and reuses same-point content. Saved data tables populate on demand.
- Attachment and HTML directories no longer become accidental chat sources. Exported originals, private settings, credentials and account-specific classification rules remain outside the public package.

Validated with 176 backend tests, JavaScript syntax and parser/geometry checks, and isolated Edge checks of exporter-root selection, files, Library navigation, chart inspection, readable text and lazy tables. Local archive detection used the real exporter index. Live ChatGPT Library downloads and unattended cloud backup runs were not exercised in this update.

## Files & Library · v1.1.4

Select the root of a [ChatGPT Exporter 2.4.1](https://github.com/kitomisaitichi-design/chatgpt-exporter/releases/tag/ChatGPT2.4.1) backup under **Export folders**, then open **Files & Library**. Search filenames and IDs; filter saved/manual/attention items or the selected chat. Saved files download locally; raster images may open inline. Source chat buttons open the matching archived conversation. File catalogs are read separately from message indexes, so Refresh detects new exporter catalog entries and imported copies without rebuilding chats.

The exporter automatically downloads Library files strictly below **10,000,000 bytes**. For larger files, follow **Find in ChatGPT**, download the original, then click **Import downloaded copy**. The Viewer checks the known size and checksum, rejects service-error files, and copies the file into its stable expected backup path. Existing copies are kept. Imported files become available locally immediately and remain included in ordinary full-folder backups. Older exporter catalogs can show saved attachments; update the exporter for manual import paths.

Files remain bounded to the selected backup root. HTML, SVG and executable content download as attachments. Large downloads stream in 128 KiB chunks. Updating preserves `.viewer-data`, shared preferences and backup/Drive configuration.

Backup ZIP compression also supports Python 3.10–3.12, retaining the same level and archive layout as the bundled Python 3.13. Scheduled backups while the viewer is closed require Windows.

Validation: **162 backend tests** and an isolated exporter-to-viewer Edge integration test, including manual import of a **10,000,000-byte** file, a byte-identical local download, Stop/resume and source-chat navigation. Website responses were simulated; live ChatGPT Library compatibility remains unverified.

## Improvements in v1.1.3

- Preferences follow new installations automatically through `%LOCALAPPDATA%\OfflineChatViewer\preferences.json`: names, folders, pins, manual order, chat highlights, sticky state, Trash, appearance, reading positions, source choices and backup preferences. Portable caches remain local. Shared personal preferences and Google credentials never ship in the public ZIP. Use `--isolated` for a separate portable archive, or `--profile PATH` for an explicit preference file.
- Chat menus provide quick rename, pin, move to folder, highlight colours, sticky priority and reversible Trash. Renaming changes the display name; original title, filename and source path remain available in Details. Trash hides chats from normal lists and cross-search without deleting their original files. Drag to Trash, hover to open its panel, drag back to restore, or use the Restore button. Distinct source files and attachments stay intact.
- Direct chat-ID lookups replace repeated catalog searches. Small catalog changes travel as row deltas; indexing-only changes do not rebuild the sidebar. Sorts retain the existing minimal-movement algorithm and scroll anchor. Quiet background tabs poll less often. Cached type rules do not repeat solely because the app version changed.
- Automatic backups have a 1–168 hour slider and exact hour input, local-only or Drive delivery, optional idle waiting, 5–120 minute idle thresholds, and an AC-power choice. Windows checks every five minutes while signed in, including with the viewer closed, and only runs a backup when its saved interval and conditions are met. Automatic backups remain opt-in.
- Google Drive detection prefers an existing `G:\My Drive`, checks other mounted drives and standard mirrored folders, and preserves a custom destination. The no-API route uses the signed-in Google Drive desktop app. Drive credentials never enter the shared preference file.
- Cleanup maintains the requested full/progress slots. Identical extra viewer ZIPs are removed only after comparing their bytes with a retained canonical ZIP. Distinct extra viewer archives move to `.retired-viewer-backups` for recovery. Unrelated ZIPs are untouched. Cleanup can run after successful backups or from its button; it does not run during an active job.

## Earlier backup improvements

- Backup progress/configuration writes use unique staging files and retry brief Windows file locks. A failed write preserves the previous saved state.
- Opening local ZIP folders works independently of saving backup preferences; the folder is created if needed and handed to Windows Explorer. Errors and results appear inside the open backup panel.
- Drive for desktop detection prefers `G:\My Drive` when present, then checks other mounted drives and common local Drive folders. It suggests `Offline Chat Viewer Backups` within My Drive. Your saved/custom choices remain authoritative; discovery never reads cloud files or initiates uploads.
- Quick scan and autofill checks nearby export markers and Downloads shallowly. Backups continue using the same loader source and upward traversal.
- Copy icons accompany export, local ZIP and Drive folder paths. Windows Browse uses the modern folder dialog with an address bar, search and Quick Access. Local ZIP creation is prominent at the top of the backup workspace.
- Attachment reference parsing no longer slows down on unmatched brackets inside saved code. Unchanged document references are cached and referenced file existence is checked again.
- Full/progress download links display actual compressed ZIP sizes. A small progress ZIP can be legitimate when only a few files changed; the first progress backup includes all source files.

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
- Sort by newest, oldest, recent update, A–Z, Z–A, least recent update, or manual order. Newest/oldest use original creation time when available, otherwise source timestamps.
- Group by categories, disk folders, or chat type; show a flat list; collapse groups; hide all project chats using the Projects checkbox.
- Dark, pure black, light, or custom background/sidebar/text/accent colors. Adjust text size, reading width, and page size.
- Optional remembered reading positions and timestamps. Recurring export rescans are off by default. In Settings, enable them and use the stepped interval slider: 5, 15 or 30 minutes; 1, 3, 6, 12 or 24 hours; or 3 days. The default interval is one hour and the viewer must be open. You can also use Resume / rescan when you save new exports.
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

## Backups, Google Drive and ZIP integration · v1.1.3

**Backups & Drive** uses the loader's current export folder and upward traversal by default. Review the file counts and boundary, choose a visible local save folder, then create full/progress ZIPs without a Google connection or schedule. They contain original Markdown, JSON/session files and saved attachments, original exporter indexes, a linked `OPEN-ARCHIVE.html` / `archive-index.json`, hashes and organization/settings. Original source bytes and relative paths are preserved. Missing links are reported.

**Google Drive for desktop · no API setup** copies the completed ZIPs to the existing synced folder you choose. Google’s desktop app uploads them and reports cloud sync status separately. Stable filenames and unchanged-content checks avoid redundant copies. The optional direct account/API route remains available for users with their own Desktop app OAuth client; it uses stable remote IDs and resumable uploads. See **GOOGLE-DRIVE-SETUP.md** for both routes and local ZIP instructions. No credentials or private account-specific files are bundled.

Choose daily or weekly idle backups when ready. Windows runs the job while signed in and on AC power, including when the viewer is closed, and does not wake a sleeping computer. **Integrate a saved ZIP** keeps newer existing chats and can optionally restore pins, folders, appearance and reading positions. Progress ZIPs include companion files and saved attachments for changed conversations; keep the full recovery base for unchanged conversations. Deleted paths are recorded without deleting current exports on import.

## Reader improvements retained from v1.0.13

- Saved line, area, bar and scatter chart widgets render locally with labels, units, legends, data and source folds. Hover or use arrow keys to inspect values; line-chart hover cards show all active series for the selected point. Unknown chart types retain a readable source fallback.
- Self-contained saved HTML apps run in an isolated frame with network access disabled. The frame grows to fit the content. Local sliders, selectors, SVG charts and saved scripts work; apps requiring remote libraries, server APIs or missing export files may remain incomplete.
- Genuine code folds are closed by default; readable text and output panels start open. Expand code to read, wrap or copy it. Unknown code languages are inferred, and shell-wrapped Python highlights both the shell wrapper and Python body. Large blocks retain readable plain text rather than blocking the reader.
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

v1.1.9 adds live-source mutation, bounded capture retry/restart, cancellation, frozen Markdown links and unchanged local/Drive ZIP reuse regressions. Validation details are recorded in the release notes.

v1.1.8: **206 backend tests**, JavaScript syntax, renderer/catalog and isolated Edge checks. Adds regression checks for busy requests, persistent claims, cross-process cancellation, isolated local/upload policies, offline delivery/restart, destination changes, ZIP corruption, retry backoff, quiet exporter updates and nested Library-only exports. Full backend, renderer/catalog and isolated Edge checks are recorded in the release notes.

v1.1.7: **188 backend tests**, JavaScript syntax checks, renderer/geometry/cache checks and combined catalog-filter/order checks. New regression coverage includes handoff-only exports, shared progress companions, historical source metadata, hash conflicts, selectable formats, hash/state/index consistency, attachment-only cross-links, omitted-file hashing, policy changes and verified migration with an offline source. Isolated Edge checks exercise content choices, source/Drive suggestions, local ZIP creation and copying to a local test destination.

The diagnostic test now allows realistic Windows loopback scheduling while still timing out a deliberately stalled endpoint. OAuth and Drive API responses are mocked; no live Google upload or unattended scheduled run is claimed for this update. Keep `.viewer-data` during app replacement. Personal preferences and archive data are verified separately from the clean portable ZIP.

## Version history

Earlier 1.0.x builds were distributed as portable/development packages. This history summarizes their recorded changes; it does not imply every version has a public GitHub release asset. The current feature descriptions above explain the retained behavior. [Published release notes](https://github.com/kitomisaitichi-design/chatgpt-viewer/releases) provide additional validation and upgrade details.

| Version | Recorded changes |
| --- | --- |
| **1.1.11** | Large-archive image timeout repair; metadata-only catalog paths; snapshot-based validated thumbnail delivery; filename alias deduplication; visible retry errors and stale-failure guards; actual saved-image browser verification. |
| **1.1.10** | Titled writing/document cards with original-body copy and expansion; preserved LaTeX/citations; lazy native and Library images; cached whole-thread gallery with wheel zoom, swipe, pan, keyboard navigation, original-prompt jumps, reduced motion and missing-file recovery. |
| **1.1.9** | Resumable verified per-file captures decouple active exports from ZIP packaging; changing files retry automatically without losing stable work; pending capture survives restart; waiting/retry feedback; unchanged capture and two-slot ZIP reuse. |
| **1.1.8** | Exporter 2.4.10 nested-root and Library-only compatibility; persistent coalesced backup queue; complete local ZIPs before Drive delivery; verified retry without rescanning, exponential backoff and cancellation; quiet exporter-update detection; visible queue/retry controls and guarded double submission. |
| **1.1.7** | Exporter 2.4.4 handoff, shared source/history and version support; selective ZIP formats; typed indexes and SHA-256 state JSON/CSV; shared progress attachments; verified existing-ZIP Drive migration; candidate autofill; filter/read-state backup restoration; adjustable saved sidebar width and refined section styling. |
| **1.1.6** | Compact catalog search; combined read/project/pin/untitled/inclusive date filters; sidebar dates and created/updated/message metadata; read revisions; quick rename and keyboard navigation; reverse alphabetical/updated sorts; filtered drags preserve hidden placements. |
| **1.1.5** | Exporter-root inspection and portable-state metadata merging; JSON preference and newer-copy import protection; per-chat searchable file previews/downloads; bounded source/Markdown caches; indexed long-chat paging; numeric chart range/extrema/gaps and lazy data tables. |
| **1.1.4** | Exporter 2.4.1 Files & Library; saved/manual/attention filters; size/hash-checked downloaded-copy imports; streamed downloads and source-chat links; Python 3.10–3.12 ZIP compression compatibility. |
| **1.1.3** | Shared preferences and encrypted backup history across versions; quick rename/pin/folder/colour/sticky menus; recoverable drag-to-Trash; catalog deltas; 1–168 hour backup interval, idle/power/local-only choices; safe extra-ZIP recovery/deduplication. |
| **1.1.2** | Clean first launch; Windows file-lock retry-safe backup state; working local-folder opening; mounted/mirrored Drive detection and autofill; modern folder dialog and path copying; ZIP-size labels; cached attachment references and linear parsing. |
| **1.1.1** | API-free Drive for desktop route; loader-matched backup discovery/traversal; actual original Markdown/JSON/attachment ZIPs and linked offline browser; visible local save folders; full/progress recovery and optional integration. |
| **1.1.0** | Deterministic local full/progress ZIPs, direct Google account route and idle scheduling; stable sidebar nodes/scroll anchors and batched drag saves; recurring scans off by default with interval controls; readable text open and improved chart inspection. |
| **1.0.13** | Saved chart and sandboxed HTML app rendering; hover/keyboard inspection; genuine code folding and language inference; fitted-table overlap repair; exact in-chat highlights and cross-chat match navigation; layered group/type/pin sorting and batched organization. |
| **1.0.12** | Shared source reads and message-specific fragments; isolated bounded syntax worker; sidebar row reuse; request cancellation/observer cleanup; indexed-status restoration; canonical type counts/manual correction and cleaner exported titles. |
| **1.0.11** | Markdown/colouring independence and automatic rendering recovery; canonical Chat/Work/Codex labels and cached receipt repairs; readable native dropdowns in black/dark/light themes. |
| **1.0.10** | Fit/wide/compact tables; saved filename chips; incomplete Python detection; formula retry; vertical text chains; exact/typo/completion search; automatic portable semantic setup and Windows runtime helpers. |
| **1.0.9** | Shell pipeline panels and unfenced JSON detection; readable Unicode/indentation; exact numeric tokens; Raw/Formatted toggle and original-text copy. |
| **1.0.8** | Render long-message prefixes before fetching the rest; delayed-table retry and scroll preservation; shell heredoc code panels with gutters, wrapping, folding and copying. |
| **1.0.7** | Python scripts containing Markdown fences inside string literals keep their code presentation and exact text. |
| **1.0.6** | Saved code/execution-output blocks and unfenced Python recognition; offline syntax highlighting; separate stdout/stderr panels; exported hyperlink/source association fixes; Tool details paging. |
| **1.0.5 / repacked** | Bounded body-download retry; Unicode-safe message fragments; worker/lazy Markdown; folding controls; wide/compact expandable tables; explicit source chips and original copying. A corrected repacked package was supplied. |
| **1.0.4** | Local diagnostics for stalled status/transfer requests, with timing and byte reports excluding private conversation text and launch tokens. |
| **1.0.3** | Database-free startup state, early Markdown titles, foreground source reading and background scan initialization repairs; offline math and source chips. |
| **1.0.2** | Selected-chat priority; separate background indexing; early manifest coverage; bounded recent-chat cache and paged messages; obsolete-request cancellation and retry. |
| **1.0.1** | Correct script MIME types; usable folder controls during delayed startup; overlapping discovery/indexing with checkpoints, pause/cancel and persisted scan scope. |
| **1.0.0** | Initial portable local Markdown/JSON/Codex reader; branches, model receipts, math/tables/code, archive search, categories/pins/preferences and optional semantic search. |
