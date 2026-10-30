# Changes

## Unreleased — 2026-10-30

- Make publishing the default skill deliverable: resolve or set up a registered Pages repository and return a verified public URL.
- Persist document IDs in the site registry so later edits keep the original directory and URL across dates and title changes.
- Report the Git commit URL for document version history; preserve the registry during repeated setup.

## Unreleased review draft — 2026-10-29

- Stage and scan a document before network work, publish only that snapshot, and verify all staged files plus the root catalog.
- Add static HTML/CSS asset preflight and streaming credential tripwires without logging matched values.
- Normalize index.htm and mixed-case entry names; refuse ambiguous entries.
- Catalog document roots once, tolerate invalid UTF-8 in titles, and support neutral site.json settings.
- Preserve custom catalog generators; replace them only with --update-generator.
- Save the target after a successful push even if Pages setup fails, and report that partial success.
- Retry transient GET failures with bounded waits; reconcile Pages POST failures through a fresh GET.
- Allow ignored checkout files while preserving tracked/untracked-change refusal.
- Add report/deck starters alongside the dashboard, generic harness pointers and owned-pointer uninstall, and preview subpath/no-store support.
- Correct CSV number handling, computed percent change, and browser download-anchor handling.
- Add regression checks, browser tooling pins, and a CI definition. CI itself has not run remotely.
- Keep personal test-drive reports outside the distributable skill.
