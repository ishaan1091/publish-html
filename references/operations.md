# Commands and recovery

Run scripts from the skill clone or through its installed symlink. Prerequisites: Python 3.10+, `git`, `gh`, authenticated github.com account, configured `user.name` and `user.email`. No pip/npm packages or site build step are required.

| Command | Behavior |
| --- | --- |
| `setup.sh [--repo OWNER/NAME] [--path PATH]` | Create/reuse a public repo, scaffold it, enable main/root Pages, verify the index |
| `publish.sh SRC [FOLDER]` | Set up if needed, publish, index, commit/push, verify, print URL |
| `publish.sh SRC --document ID --replace` | Intentionally replace that folder, deleting obsolete assets inside it |
| `publish.sh SRC [FOLDER] --dry-run` | Validate source and display plan, without network or writes |
| `--repo OWNER/NAME` / `--repo NAME` / GitHub URL | Override the saved target; bare name uses authenticated owner |
| `--path PATH` | Override saved/default checkout |
| `--timeout SECONDS` | Deployment wait, default 180 |
| `--no-wait` | Push without live verification; URL is expected, not verified |

Setup and publish save the target immediately after a successful push, before Pages configuration. A Pages error is reported as pushed but deployment unverified. The publisher honors an existing saved target; specify `--repo` when switching accounts/sites. Repository defaults never use the skill author's identity. `gh` handles credentials; no tokens are stored by this skill. The installer does not log in, clone a site, create a repository, or publish anything.

Source handling:

- One HTML file becomes `FOLDER/index.html`. Use a directory if it references other assets.
- A directory is copied with all its files and hierarchy. If it has no root `index.html`, a file listing is generated.
- A non-HTML file is copied under its original name with a generated file listing.
- New documents use today's local `YYYY-MM-DD` plus a slug from the HTML title (or source name). Pass a stable `--document ID` to register this folder. Subsequent publishes with that ID reuse the original folder across dates and title changes. Without an ID the title slug is the identity. An explicit folder supports older unregistered documents.
- Custom folder names can be nested and need not be dated. Undated documents are listed after dated documents. Hidden paths, traversal, site infrastructure folders, symlinks, credential-like files, and oversized inputs are refused. `index.htm` and mixed-case entry names normalize to `index.html`; multiple entry candidates are refused.
- The copied staging tree is scanned and hashed before network work; only those bytes are published. `--dry-run` reports its manifest without GitHub, checkout, or configuration mutations (temporary staging is used). Every staged file and the root index are verified after deployment.
- `scripts/check.py` checks known HTML/CSS references and basic structure. See security.md for limits, including runtime-built URLs and external resources.
- Repeating identical inputs is a no-op commit. Changing an existing folder requires `--replace`, which does not touch siblings. Never use the site checkout itself as source.

Failure recovery:

- **Authentication:** run `gh auth login --hostname github.com`. Stop until it succeeds.
- **Dirty checkout:** preserve/commit changes yourself. The publisher does not stash or discard them.
- **Existing unrelated repo/site:** choose a new empty dedicated repo (README/license/ignore-only repositories are also accepted). The publisher does not adopt or overwrite a populated unmarked site, or change a private repo to public.
- **Push rejected:** it rebases and retries once for a non-fast-forward rejection. Unresolvable content conflicts stop with local commits intact. No force-push.
- **Pages settings differ:** review the settings and explicitly decide on any migration. The script stops instead of silently changing an existing deployment configuration.
- **Deploy timeout:** the commit may already be public. Check `gh api repos/OWNER/REPO/pages/builds/latest` and the Pages settings. Report the expected URL as unverified. Re-run safely after correcting the build problem.
- **Interrupted operation:** inspect `git status` in the site checkout. A completed local commit is retained; a dirty partial copy requires review before retry. Idempotence covers successful runs and clean retry states, not transactional rollback of every network or process failure.

The root catalog is generated output. Customize its generator, not the generated HTML. The site's generator is preserved and executed on each regeneration. Use `--update-generator` only to replace it deliberately with this skill's version. `site.json` is user-owned and preserved; it controls title, description, lang, nav, author, footer, accent/dark_accent, and catalog labels. It cannot translate the document content itself.

Shared page comments are optional and off by default. See [comments](comments.md) for Giscus setup. Publishing does not contact Giscus; its availability never gates a deployment. The publisher injects a managed embed into the staged entry page only when the site has valid enabled configuration, then hashes/verifies the resulting bytes.


Additional commands:

```sh
./setup.sh --repo OWNER/reports --dry-run
python3 scripts/check.py /path/to/document --json
python3 scripts/new.py /tmp/deck --type deck --title "My explanation"
python3 scripts/preview.py /path/to/document --base /reports/
python3 scripts/install.py --skill-dir /exact/harness/skill/destination
python3 scripts/install.py --harness both --uninstall
```

The installer only removes symlinks belonging to this clone and its owned Codex block; it retains backups. No harness location is guessed. Preview binds localhost and sends Cache-Control: no-store. Setup dry-run does not contact GitHub.

GET API calls retry HTTP 429/502/503/504 at most twice with bounded waits. Permission errors stop immediately. A failed Pages POST is reconciled through GET; arbitrary mutations are not blindly retried.

Current limits: one saved default target; no lifecycle list/status/move/remove commands yet. The no-hand-rolled-git instruction applies to publishing, not to all possible repository maintenance. If a requested maintenance action lacks a script, report the missing capability instead of inventing a command. Replacement uses a same-filesystem backup/rename with exception recovery, not a crash-proof transaction. After abrupt process loss, inspect the checkout and any .publish-swap-* backup before retrying.


Repository registration is automatic, not a separate user setup step. `publish.sh` reads the saved config first. With no registration it uses the authenticated owner's `reports` repo, creating it and Pages if missing. On later invocations it uses the saved target, including cloning that repo again if the checkout was removed. It does not create one repository per document.

Document registration lives in the site's `.publish-html.json`, as additive `documents` metadata on the existing version-1 marker. Each stable ID maps to one directory and title. Revisions overwrite the working-tree files of that document through `--replace`; Git commits retain prior versions. Progress includes a GitHub commit URL. Replaying identical content and identity makes no new commit.
