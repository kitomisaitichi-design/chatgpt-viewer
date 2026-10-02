# Viewer 1.1.5 validation

176 backend tests cover exporter job/index merging, filename metadata, wrapped ZIP imports, JSON/Markdown preference, preserving a newer existing copy, manual unpin/rename persistence, stale metadata timestamps, partial attachments, bounded preview and streamed downloads, file path boundaries and attachment JSON exclusion. Randomized paging comparisons cover hidden tool messages and before/after/around queries. Cached paging is verified without a second full-source iteration.

Frontend checks exercise the actual bundled Markdown parser and worker cache, JSON large-integer preservation, 100,000-point numeric ranges and sampled outliers/gaps, nearest-point selection on uneven numeric axes, and existing layered-order/type/highlighting checks. All app JavaScript passes syntax checks.

Isolated Edge validation covers the detected export parent, matching folder traversal, saved/unavailable files, literal HTML in text previews, navigation to Files & Library, keyboard chart inspection, a 60,000-point chart with a late outlier and no individual point circles, lazy data tables and open readable text without code gutters. These fixture chats are outside the package and personal installation.

A local microbenchmark with 50,000 cached source rows and 1,000 around-page requests took 1.5 ms with indexes versus 1,641.8 ms for repeated linear filtering. This measures in-memory paging only; it is not an end-to-end startup or network benchmark.

The real exporter folder inspection found 719 indexed entries, 708 saved conversation files, 11 missing files and 19 entries awaiting attachments. Original export content was not modified. The personal installation's cached chats, full organization, settings and backup/Drive files are compared before and after replacing app files.

This release builds on the published v1.1.4 Files & Library implementation. It does not claim a new live-account ChatGPT download test or unattended Google Drive backup test.
