# Offline Chat Viewer v1.1.3 verification

155 backend tests passed, including cross-version shared preferences, concurrent profile writes, preserving source names and original bytes, Trash surviving reindexing, restore, validated colours, row-delta transfer, configurable local-only schedule gates, task XML, shared encrypted backup history and backup recovery/deduplication. Existing frontend checks passed for layered sorting, type filtering, highlighting, minimal sidebar moves through 150 permutations, scroll anchoring, readable text and all nine rescan intervals. All modified JavaScript passed syntax checks.

Live Edge checks used an isolated two-chat archive and a separate preference file: renamed a chat, set its colour, moved it to Trash, opened Trash and dragged it back into its original group. The backup panel detected G:\My Drive, accepted a six-hour custom interval and optional idle/power/local-only choices, and created the two local ZIP slots. Test conversations and preferences are excluded from the portable package.

Personal installation was updated while closed. Its 704 conversations and existing organization/preferences were retained; shared preference migration stays on this computer. Original exporter files were not edited. Existing full and progress archive ZIPs were retained; this release did not rebuild or upload the multi-gigabyte personal archive.

Scheduling XML and interval conditions were tested without enabling a real recurring test task. Actual Google Drive cloud upload and an unattended scheduled Windows run were not exercised.

