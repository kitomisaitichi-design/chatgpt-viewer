# Saved dynamic content

The Viewer renders saved data locally. Versions 1.1.31–1.1.32 extend its existing Chart, flowchart, table, image-collection and card renderers; ordinary code examples remain literal.

## New supported components

- `table`, `data-table` or `Table content={...}`: supplied rows and labels become a locally sortable/filterable table with a Copy button. Sorting cycles through ascending, descending and original order. Copy exports all matching rows as TSV. Large tables page through 100 rows at a time instead of constructing the entire DOM at once; previews above 64 columns retain their full source with a visible note.
- `newspaper`, `columns`, `column`, `article`, `section`, `panel`, `stack`, `heading`, `paragraph`: responsive mixed layouts with multiple reading columns on desktop and one column at narrow widths. Columns can contain text, tables, bars, charts and controls.
- `status`, `status-badge`, `icon`, and inline `[OK]`, `[WARN]`, `[FAIL]`, `[PENDING]` and similar labels inside structured content: preserve the actual words/symbols and apply theme-aware semantic colors. Explicit text/badge colors are also retained. Static statuses do not pretend to be live operation results.

- `bar`, `meter`, `progress`, `progress-bar`: thin horizontal tracks with supplied labels, values, limits, units, colors and qualitative captions. Missing or nonnumeric values remain readable without inventing a score or animating a fake loading state.
- `comparison`, `bars`: grouped labeled comparisons, responsive to the reading width.
- `copy`, `copyable`, `code-block`: readable saved text with a working Copy button. Copy preserves line breaks and literal code delimiters; a failed clipboard write displays a failure rather than claiming success.
- `tabs` with `tab` or `tab-panel`: local tab switching, including Left/Right, Home and End keyboard navigation and accessible tab/panel relationships.
- `accordion`, `details` and `summary`: native expandable saved content.
- `button`: explicit `action="copy"` with a saved text/value, or a saved URL, performs the corresponding local action. Other application actions remain labeled and disabled; exported `onclick` expressions are never executed.
- `Chart` inside grids, cards and boxes: uses the same data-aware chart renderer and its series, inspection, expanded view and saved-data controls as standalone charts.
- Layout attributes: bounded width, height, gap, padding, radius, background, border, alignment, flex and clipping. Empty styled boxes can represent thin bars rather than being forced into large cards.

For example:

```jsx
<comparison>
  <bar label="Visual consistency" value={98} max={100} valueLabel="Very strong" color="pink"/>
  <bar label="Unmeasured quality" valueLabel="Not established"/>
  <caption>Qualitative illustration, not a measurement.</caption>
</comparison>

<tabs label="Views">
  <tab title="Summary"><copy label="Example" text="Reusable saved text"/></tab>
  <tab title="Details"><accordion title="Notes"><text>Saved notes</text></accordion></tab>
</tabs>

<newspaper columns={2}>
  <article><heading>Findings</heading><paragraph>[OK] Arbitrary saved text ✓</paragraph></article>
  <column><Table content={{"columns":["Name","Status"],"rows":[{"Name":"Example","Status":"[OK]"}]}}/></column>
</newspaper>
```

These are supported Viewer examples, not a claim that every ChatGPT model exports all these tag names. A bounded sample of recent saved conversations confirmed nested Chart components and layout sizing attributes. The additional bar/control primitives are tested with synthetic fixtures and the user's visual reference; exact serialization may vary between exports.

## Preservation and compatibility

Unknown wrappers retain their readable children and known siblings. Unsupported and malformed components retain their inert source for inspection. JSON and JSX attributes are parsed as data, not evaluated. Code fences and inline examples stay literal, including code delimiters embedded in a copyable value.

Older image syntax, grouped newer image collections, normal Markdown tables, citations, document links and source-aware attachment opening continue through their existing renderers. No new runtime dependency is required.
