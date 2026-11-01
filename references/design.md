# Design and interaction contract

Start with the supplied content and the shape of the information. State its central finding early; do not invent a conclusion. Use a few deliberate visual choices consistently: display and body type, spacing scale, background surfaces, accents, and borders. Use system fonts or bundled relative font assets. Preserve a supplied visual identity; otherwise choose a style suited to the subject. Avoid filling every report with the same KPI cards.

## Choose a representation for the reader's task

Before laying out a long explanation, rank the reader's likely difficulties: for example, identifying what belongs to a system, following a process, comparing options, or understanding how evidence supports a conclusion. Review supplied visuals and controls first; keep or improve what already helps, and add only explanations that address a real difficulty. Arrange them along a coherent reading path instead of layering them onto dense surrounding prose. Record the choices briefly in working notes; do not add an approval step or a required page section. Existing controls are not a reason to add more.

Use the supplied content to choose among prose, a static visual, and interaction:

| Information shape | Useful representation | Prefer prose or a static form when… |
| --- | --- | --- |
| System boundaries, components, dependencies | Labeled system/context diagram with explicit boundaries and relationships | There are few parts or the relationships are easier to state directly |
| Process, sequence, branching | Numbered flow, sequence diagram, or branch map showing a representative path and decision points | The process is short and a concise ordered list is clearer |
| State transitions and failure outcomes | State diagram or transition table with triggers and outcomes | There are only a few states and a compact table is enough |
| Alternatives or categories | Comparison table or aligned small multiples, with shared criteria | There are few alternatives and prose captures the meaningful distinction |
| Quantitative trends | Chart with units, labels, source context, and a readable data table or text equivalent | The values are sparse or exact lookup matters more than the pattern |
| Assumptions, uncertainty, limitations | Visible annotations next to the relevant claim or result | The caveat is brief; keep it beside the claim rather than hiding it |

Interaction earns its complexity only when changing a view, input, or step reveals something useful—for example, tracing a selected route through a complex process or recalculating supplied values under clearly labeled assumptions. If the reader needs to see one main explanation, use a static diagram, table, or prose. A diagram can be useful without interaction. Do not add controls for decoration, a widget for every section, a mandatory template, numeric widget quotas, or scroll-gated animation.

Selected visuals should replace or summarize dense prose and keep the essential explanation visible. Put secondary detail behind a disclosure only when readers may reasonably need it on demand. Avoid repeating long descriptions around each visual; provide concise labels and a text alternative that preserves the same essential information.

For example, a technical architecture explanation may need a boundary diagram followed by one representative process path, with detailed caveats kept near the relevant step. A numerical comparison with supplied data may be clearest as a labeled comparison table or chart, without controls unless changing an input reveals a meaningful alternate view. A short narrative with no repeated structure or decision task may be best left as prose.

For each selected visual or control, check that a reader can identify the components and boundaries and follow a representative path where relevant; each control causes a meaningful and correct change; and the explanation remains usable on mobile, with a keyboard, under reduced-motion preferences, in print, and as text. Keep evidence traceable to the supplied sources and values, and label assumptions. This is a review of the chosen explanations, not a requirement to add a widget or a separate user-facing checklist. Use plain HTML/CSS/JS; no browser bundle or build dependency is needed.

Build accessible native controls. Every input needs a visible label, buttons need meaningful text, keyboard focus must be visible, and charts need textual values or an equivalent data table. Color cannot be the only signal. Use `prefers-color-scheme`, `prefers-reduced-motion`, responsive layouts, and usable print styles where relevant. Keep mobile tables scrollable without making the entire page overflow.

Choose widgets by the job they do:

| Reader's job | Useful interaction | Implementation |
| --- | --- | --- |
| Compare alternatives | Sort/filter, show detail | Native select, search input, details |
| Explore assumptions | Slider or numeric input | One state object; recompute derived values and all views |
| Understand a trend | Inspect points, change period | Inline SVG and a readable table; canvas for dense plots |
| Read a deck | Previous/next, keyboard navigation | Semantic sections, buttons, fragment links, print all slides |
| Bring their own data | File input, validation, reset | File API; parse locally, show errors, do not upload implicitly |
| Take results away | Export current filtered view | Blob download; escape CSV quotes and formula prefixes |

Use `assets/dashboard.html` as working code to adapt, not as a generic substitute for design. Its controls share one state object and rendering pass; the table and chart agree, no matches has an explicit state, and export follows the active filter. For deck layouts or other widgets, implement the small amount of JS the task actually needs.

Keep untrusted text out of `innerHTML`; use `textContent` and DOM creation. Do not interpolate raw user strings into inline JS. Never put API credentials in client code. A password field or hidden JavaScript variable does not make a public page private. Use relative assets to keep documents portable between localhost and a Pages project subpath.

Verify interactions by observable outcomes: slider changes computed totals; combined filters give correct rows; reset restores defaults; export matches displayed data; all important actions work from the keyboard. Inspect mobile and desktop and check the console. Label sample data and assumptions. State what wasn't tested. A visually attractive screenshot does not prove that widgets work.


Choose a starting form explicitly (`new.py --type report|deck|dashboard`) or create the HTML directly. For a supplied technical explanation, consider a reading layout, architecture diagram, walkthrough, and code atlas. Match the form to the content.

For large data, measure browser work: debounce expensive search, page or virtualize long tables, compress images, and avoid embedding large binary assets as base64. Do not add virtualization or a charting dependency until the document's size and interaction justify it.
