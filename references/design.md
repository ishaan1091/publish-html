# Design and interaction contract

Start with the supplied content and the shape of the information. State its central finding early; do not invent a conclusion. Use a few deliberate visual choices consistently: display and body type, spacing scale, background surfaces, accents, and borders. Use system fonts or bundled relative font assets. Preserve a supplied visual identity; otherwise choose a style suited to the subject. Avoid filling every report with the same KPI cards.

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
