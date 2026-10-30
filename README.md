# publish-html

A portable agent skill for turning **supplied content** into polished interactive HTML and publishing it to a remembered GitHub Pages repository. It does not perform the underlying research. The skill source and each user's hosting repository are separate.

**PUBLIC INTERNET: never publish secrets, credentials, or work-confidential data. All published files and Git history are public.**

## Install

Requirements: macOS, Linux, or WSL; Python 3.10+, Git, authenticated [GitHub CLI](https://cli.github.com/), and configured Git author identity. No runtime npm/pip dependencies or site build step.

This distribution is pending final publication review. Once its GitHub repository is published:

```sh
git clone https://github.com/ishaan1091/publish-html.git
cd publish-html
python3 scripts/install.py --harness both
```

Use `--harness claude`, `--harness codex`, or `--skill-dir /exact/harness/skill/path`. Installation creates pointers to one shared implementation, preserving unrelated instructions. Reinstalling is safe. Keep the clone at a stable path. Installing alone publishes nothing.

## Create and publish

Ask your agent:

> Use publish-html to turn the analysis above into an interactive report and publish it.

The agent designs HTML for the supplied material, checks interactions, and publishes through the scripts. Optional starters are examples, not fixed layouts.

```sh
gh auth status --hostname github.com
python3 scripts/new.py /tmp/my-report --type report --title "My public report"
python3 scripts/check.py /tmp/my-report
./publish.sh /tmp/my-report --document my-report
# Later revisions keep the same URL:
./publish.sh /tmp/my-report --document my-report --replace
```

Destination priority: explicit `--repo OWNER/REPO` (or GitHub URL), saved registration, then `<authenticated-user>/reports`. Registration lives at `${XDG_CONFIG_HOME:-~/.config}/publish-html/config.json`, outside this clone. The default checkout is `~/projects/OWNER/REPO`. The publisher refuses to host output in this skill repository.

Each document gets its own directory and assets. Stable IDs retain URLs across title/date changes. Git preserves revisions; identical runs create no new commit. A responsive light/dark catalog lists documents. Every staged file and the catalog are checked against live bytes before success. The public URL is the final stdout line.

```sh
./setup.sh --repo https://github.com/YOUR_USER/your-site
./publish.sh /tmp/my-report --document my-report --dry-run
```

Existing initialized repositories with only README/license/ignore files can be registered. Populated unmarked sites and incompatible Pages configurations require a deliberate migration; they are not overwritten.

## Optional comments — no backend to deploy

**Skip this entirely to publish pages with stable URLs and Git history. No GitHub sign-in is required to read any page.**

Opt into page feedback using [Giscus](https://giscus.app/) and GitHub Discussions:

```sh
./comments.sh setup
# Install the Giscus GitHub App for the hosting repo when prompted;
# choose an existing Discussion category (prefer Announcements):
./comments.sh setup --category Announcements
./publish.sh /tmp/my-report --document my-report --replace
./comments.sh pull my-report
./comments.sh reply my-report COMMENT_ID "Updated the explanation and republished."
```

Only commenters sign into GitHub. Comments remain in Discussions through page updates. The agent reads feedback and replies using `gh`; replies appear under that authenticated account with AI attribution. Setup is optional and incomplete setup does not block publishing. There is no custom backend, Cloudflare account, or separate browser token. See [comment setup and feedback](references/comments.md).

## Verification and maintenance

```sh
python3 -m unittest discover -s tests -v
npm ci --prefix tests
cd tests && npx playwright install chromium && npm test
```

Browser tooling is development-only. See [operations](references/operations.md), [design](references/design.md), and [security](references/security.md). Uninstall owned pointers with `python3 scripts/install.py --harness both --uninstall`; existing instruction backups are retained.

Limits: GitHub.com main/root Pages; one remembered default target; macOS/Linux/WSL, not native Windows; 50 MiB/file and 200 MiB/publication; scanning is not a confidentiality guarantee. Comments depend on GitHub and hosted Giscus, are page-level, and have no text anchoring or resolved state. Git versions are retained in history, not separate permanent Pages URLs for every revision. MIT license; publication remains pending final owner review.
