# Finding conversations quickly

Press **Ctrl+K** and type part of a chat title. The default **Chat titles · fast** mode searches cached conversation metadata immediately, then fills any gaps from the local server. It does not read message bodies.

Use **Up/Down** to select a result and **Enter** to open it. **Clear** empties the query; **Escape** closes the finder. Titles are accent-insensitive, and both the displayed name and original name remain searchable after a rename. Exact titles/IDs and literal phrases rank above prefix and word matches. Labeled typo suggestions are a fallback when no literal matches exist.

Choose a chat type or category to narrow results. For words inside messages, use **Search message contents** or select an existing full-text mode. Deep searches show their loading state, and typing or closing cancels stale requests.

The sidebar's **Find title or folder** field also updates on an animation frame. Enter resolves the latest query before opening a matching conversation.

## What changed in 1.1.33

- Cached normalized metadata avoids rebuilding every title/project/folder string on each filter pass. Renames and changed metadata invalidate the affected entry.
- A bounded top-result list avoids sorting every title match. Typo fallback has input-length and candidate limits.
- Structured layout recognition reuses its parsed data. Repeated extraction uses immutable cached results, bounded to 24 entries and an 8 MiB estimated serialized-data budget; larger results bypass caching.
- Existing renderer workers, viewport scheduling and progressive batches continue to control long conversations. Short panel/control transitions respect the operating system's reduced-motion preference.

## Measured comparison

Measurements compare 1.1.32 and 1.1.33 on identical synthetic data in the same local environment. They describe the specific operation measured; they do not imply total loading or paint time, and results vary by archive size and hardware.

| Operation | 1.1.32 | 1.1.33 | Method |
| --- | ---: | ---: | --- |
| Title query to matching DOM result | 304.2 ms | 2.3 ms | Median of three queries against the same 1,000-chat browser demo |
| Warm sidebar filter, 50,000 chats | 41.0 ms | 20.2 ms | Median repeated model-filter timing with identical catalog/query |
| Cold extraction, 120 structured cards | 4.84 ms | 3.82 ms | Same 13,005-character fixture |
| Warm repeated extraction of that fixture | 1.137 ms | 0.001 ms | Median parser/extraction timing; cache lookup only after the first parse |

The title benchmark measures availability of a matching result in the DOM, not the subsequent browser paint. The extraction benchmark excludes DOM rendering and media decoding. The 50,000-chat title lookup itself measured 43.3 ms warm; the 2.3 ms browser result should not be extrapolated to that larger dataset.

Tests also protect hidden-chat exclusions, original titles, scope filters, stale-success/error cancellation, repeated Enter, empty input, code/fence preservation and malformed structured-content fallbacks. Browser verification used an isolated demonstration archive rather than personal chats.
