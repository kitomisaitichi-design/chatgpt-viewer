# Backups and selection

Use Ctrl/Command-click, Shift-click, All visible, Invert visible or Select subagents in the sidebar, then **Back up selected**. Preview lists the exact chat set, source bytes before compression, saved attachments, unavailable links and local destination. Keep Markdown or JSON/session data; review again after changing formats. Create selected ZIP queues this fixed selection and folder, without changing full-archive schedules or automatically uploading it. Completed local jobs appear under **Backups & Drive → Selected backups**, with size, date and a checksum in the download tooltip.

Shared JSON sources are scoped to the selected chat objects. JSON retains branches, citations and saved metadata; Codex sessions retain producer and subagent metadata. Linked local files are captured and their references are rebased within each chat's package. Unavailable files appear in the manifest. Markdown retains supported table/code syntax. Importing a selected ZIP uses the existing newer-copy and identity rules.

The health summary separates the last local save from the last confirmed delivery and the running/scheduled state. A local ZIP is verified against its saved hash before publication; files changed since verification require rechecking. Missing/changed recorded ZIPs are not offered as valid downloads. A checksum failure pauses automatic delivery retries and directs you to **Create local ZIPs**. Existing ZIPs remain on disk while replacements are prepared and hashed.

Retry resumes a valid completed delivery; it does not silently approve a changed destination. Cancel stops active/queued work and pauses pending delivery. Completed ZIPs and originals remain. Repeated control activation is guarded and backend queue intents survive restart. Backup operations retain existing source boundaries, available linked files and format choices.

For modern features beyond this release, the most useful additions are a restore preview that shows new/duplicate/conflicting chats before import, optional restore-verification history, and searchable job receipts. Those should use existing manifest checks and expose actual results rather than inferred completion.
