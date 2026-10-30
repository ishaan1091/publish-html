# Project guidance

This repository contains the portable `publish-html` skill. Its user-facing workflow is in `SKILL.md`; keep the installer pointers and README consistent with it.

- Invoking the skill for a deliverable includes creating/verifying HTML, publishing through `publish.sh`, and returning a verified public URL. Honor an explicit local-only/no-publication instruction.
- Resolve the saved repository registration first; create the authenticated user's public reports repository and Pages only when needed. Reuse that target on subsequent invocations.
- Each document has a stable ID and its own directory. Edits keep the original public URL and are versioned through Git commits. Do not create a new dated directory for each revision.
- Do not publish secrets or employer/work-confidential content. Keep credential handling in `gh` and local configuration outside this repository.
- Keep runtime scripts Python standard-library-only and site output plain HTML/CSS/JS. Optional browser tooling is development-only.
- Keep shared development artifacts under `agents/`. Personal reports and research belong outside the distributable skill directory.
- Transform supplied content only; do not independently research the underlying subject.
- Comments are optional and off by default. Publishing and stable URLs must work without Giscus.
- Publishing an HTML deliverable does not authorize committing or publishing this skill repository itself.

Checks appropriate to publishing changes:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check.py /path/to/document --json
# For starter or browser behavior changes, with dev tooling installed:
npm test --prefix tests
```

Use temporary/fake repositories for automated tests. Only perform live GitHub writes when the task authorizes publication. Never force-push or discard user changes.
