# Local ZIPs and Google Drive backups

The reader and local ZIP creation work without a Google account. Cloud backups and scheduling start off. Open **Backups & Drive** in the sidebar.

## Create an actual local archive

1. Leave **Use the loader’s folder and traversal** checked. The backup uses the current **Export folders** selection and upward depth; later changes there apply to the next backup. Uncheck it only to choose a separate backup source.
2. Select **Review files to include** to see the boundary, Markdown/JSON/session counts, saved attachments and source size.
3. Choose a **Local ZIP folder**. The default is a visible `Backups` folder next to the viewer's data folder. Select **Full archive + progress**, then **Create local ZIPs**. This action does not require or enable a Google connection or schedule.
4. When **Local ZIPs ready** appears, use **Open local ZIP folder** or the download links. Extract the whole ZIP before opening `OPEN-ARCHIVE.html`.

Each ZIP contains the original saved documents and attachments under `archive/`, the original exporter indexes where present, `archive-index.json`, a browsable `OPEN-ARCHIVE.html`, `backup-manifest.json` with file hashes and unavailable links, and viewer organization/settings. Markdown and JSON bytes are preserved. The original folder layout keeps saved relative links intact. The generated index links each conversation to its saved Markdown, JSON and available attachments, and lists all included files.

The loader's exclusions and traversal limits are shared by backups. Standard attachment folders and locally linked assets are added within that boundary. The viewer's data/cache, local backup destination and sync destination are excluded. Exporter error-response files and a duplicate outer `attachments.zip` are not copied when the saved attachment tree is available. A remote attachment that the exporter did not save cannot be recreated; unresolved links are reported.

**Full:** every discovered source document and available attachment in the chosen scope. **Progress:** files changed since the last successful delivery to the selected cloud destination, or since the last local backup for local-only creation. Changed conversations bring their companion Markdown/JSON and saved linked attachments; exporter metadata is included with changes. The first progress ZIP contains all files. Keep the full ZIP as the recovery base for unchanged conversations. Progress means saved changes, including unfinished content if the exporter saved it; it does not guess how complete a conversation is. Deleted paths are listed without deleting current exports on import.

## Google Drive for desktop: no API setup

1. Install [Google Drive for desktop from Google](https://www.google.com/drive/download/) and sign in to your chosen account in that app.
2. Choose a folder Google Drive syncs: a folder in your mirrored or streamed My Drive, or a local folder configured with **Sync with Google Drive**. Google explains these options in its [streaming and mirroring guide](https://support.google.com/drive/answer/13401938).
3. In the viewer choose **Google Drive for desktop · no API setup**. It detects mounted My Drive folders and prefers `G:\My Drive` when present, suggesting `G:\My Drive\Offline Chat Viewer Backups`. The dedicated subfolder is created when you actually copy ZIPs. **Quick scan & autofill** refreshes suggestions without replacing your own folder choices. **Choose synced folder…** opens the modern Windows picker at that location. The viewer cannot turn an arbitrary local folder into a synced Google folder by itself.
4. Select **Copy ZIPs to Drive folder** for an immediate backup. Completed ZIPs are first built locally, then copied into the selected sync folder. Google Drive for desktop performs the cloud upload; check that app's sync status to confirm it finished.
5. For automatic backups choose **Full archive + progress**, **Every 24 hours** and your idle time. Check **Enable automatic Google Drive backups**, then **Save backup preferences**. Weekly and single-ZIP modes are also available.

This route needs no Google Cloud project, client JSON or API authorization in the viewer. It keeps `Chat-Archive-Full.zip` and `Chat-Archive-Progress.zip` as the same destination filenames. Unchanged files skip copying. New content changes the SHA-256; a content hash cannot stay the same while its contents change. Google controls cloud file IDs, revision behavior and sync status for this route. The viewer reports **Copied to Google Drive folder**, which confirms the local copy, not a finished cloud upload.

## Optional direct account route

Choose **Direct account · optional API setup** only if you want the viewer to upload directly instead of using Google Drive for desktop.

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select your project and enable **Google Drive API**.
2. Configure Google Auth Platform audience and contact details. Add your account as a test user if using an external app in Testing.
3. Create an OAuth **Desktop app** client and download its connection JSON. A web or service-account client will not work.
4. Import that JSON in the viewer, select **Connect Google**, and complete Google's official sign-in and permissions yourself. The viewer never asks for your Google password.
5. Browse/select a Drive destination or paste its folder link. Save preferences, then select **Back up to Drive now** or enable the idle schedule.

The optional API route uses stable Drive file IDs, resumable uploads and size/MD5 confirmation. Tokens and upload checkpoints are protected locally for the current Windows user and excluded from ZIPs. No shared account or credentials are bundled. Google's external Testing mode can expire refresh tokens after seven days for these permissions; a suitable Production audience or later reconnection may be needed. See [Google's desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app) and [token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

## Scheduling, recovery and portability

On Windows the idle schedule registers a task for the signed-in user. It checks for a due backup on AC power, including while the viewer is closed, and runs after at least 24 hours since the last successful copy/upload (seven days for weekly). Active use stops an idle job; completed backups are kept. It does not wake a sleeping computer. An off/asleep or busy computer waits for a later idle opportunity. Google Drive for desktop must be signed in and running for its cloud upload to finish.

Keep the viewer at the same location after enabling the task. To move it, disable the old schedule, move the app and `.viewer-data`, then enable the schedule from the new installation. Reconnect the optional API route when changing PC/Windows user. For desktop sync, select a synced folder on the new PC.

**Integrate a saved ZIP** imports new/newer conversations and their saved attachments. Existing newer conversations are kept. Restore backed-up pins, categories, appearance and reading positions with the optional checkbox. Original exports are never rewritten.

A completed ZIP is replaced only after its replacement finishes. If a backup fails, inspect its phase/error, fix the folder or space issue and retry. Conversation ZIPs contain readable personal data and are not password encrypted. Keep personal backups separate from the shareable application package.

Release checks cover original-file preservation, linked index targets, loader traversal, progress companions, desktop folder copying/cancellation and optional API mock responses. No live Google account or cloud upload is claimed in release validation.

## ZIP sizes and folder controls

Download links show each ZIP’s actual compressed size. A full archive includes all discovered saved documents and attachments. A progress ZIP includes changes since the last successful backup and may be small when little changed; its first run includes everything. **Review files to include** shows the full source scope and source size before compression.

Copy folder paths with the adjacent copy icon. **Open local ZIP folder** opens Explorer independently of saving settings, creating the local folder if needed. Its result or any error appears within the backup dialog. State-file writes retry brief Windows sharing locks and preserve the previous saved file if replacement fails.


VERSION 1.1.3
Preferences automatically follow new installs for the same Windows user. Keep .viewer-data when updating to preserve the index. Conversation menus include colours and reversible Trash. Backups support every 1-168 hours, optional idle/AC-power conditions and local-only delivery. Extra distinct viewer ZIPs move to .retired-viewer-backups; exact duplicate copies can be removed. Automatic backups remain off until you enable and save them.
