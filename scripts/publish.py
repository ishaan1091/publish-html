#!/usr/bin/env python3
"""Portable GitHub Pages publishing. No third-party Python dependencies."""
import argparse
from contextlib import contextmanager
import datetime as dt
try:
    import fcntl
except ImportError:
    fcntl = None
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError

SKILL = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "publish-html"
MARKER = ".publish-html.json"
RESERVED = {"scripts", "node_modules", "index.html", "readme.md", "comments.js", "cname", "404.html", "site.json"}
spec = importlib.util.spec_from_file_location("catalog", SKILL / "scripts/gen-index.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
spec_check = importlib.util.spec_from_file_location("static_check", SKILL / "scripts/check.py")
static_check = importlib.util.module_from_spec(spec_check)
spec_check.loader.exec_module(static_check)


class Error(Exception):
    pass


def log(message):
    print(message, file=sys.stderr, flush=True)


def run(*args, cwd=None, check=True, data=None):
    env = {**os.environ, "GH_HOST": "github.com", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
    p = subprocess.run([str(a) for a in args], cwd=cwd, input=data, text=True,
                       capture_output=True, env=env)
    if check and p.returncode:
        # Output is diagnostic only. Never print source contents or credentials.
        raise Error(f"{args[0]} {args[1]} failed:\n{p.stderr.strip() or p.stdout.strip()}")
    return p


def git(repo, *args, **kwargs):
    return run("git", *args, cwd=repo, **kwargs)


def api(endpoint, method="GET", body=None, missing_ok=False):
    args = ["gh", "api", endpoint, "--method", method]
    if body is not None:
        args += ["--input", "-"]
    for attempt in range(3):
        p = run(*args, check=False, data=json.dumps(body) if body is not None else None)
        if method != "GET" or not p.returncode or not re.search(r"HTTP (429|502|503|504)", p.stderr) or attempt == 2:
            break
        time.sleep(2 ** attempt)
    if p.returncode:
        if missing_ok and "HTTP 404" in p.stderr:
            return None
        raise Error(f"GitHub API {method} {endpoint} failed: {p.stderr.strip()}")
    return json.loads(p.stdout) if p.stdout.strip() else {}


def slug(text):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:72].rstrip("-") or "document"


def safe_folder(value):
    p = PurePosixPath(value)
    if (p.is_absolute() or not p.parts or str(p) != value or
            any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", s) or s.startswith(".") for s in p.parts) or
            p.parts[0].lower() in RESERVED):
        raise Error("Destination must be a relative folder, e.g. 2026-10-29-report or archive/report; no traversal or reserved folders.")
    return p.as_posix()


def inspect_source(value):
    source = Path(value).expanduser().absolute()
    if source.is_symlink() or not source.exists():
        raise Error("Source must exist and cannot be a symlink.")
    files = sorted(source.rglob("*")) if source.is_dir() else [source]
    total = 0
    for path in files:
        rel = path.relative_to(source) if source.is_dir() else Path(path.name)
        if path.is_symlink():
            raise Error(f"Symlinks cannot be published: {rel}")
        if any(p.startswith(".") or p in {"node_modules", "__pycache__"} for p in rel.parts):
            raise Error(f"Hidden files, dependency folders, and caches cannot be published: {rel}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise Error(f"Source contains a non-regular file: {rel}")
        if path.name.lower() in {"credentials", "credentials.json", "id_rsa", "id_ed25519"} or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            raise Error(f"Potential credential file cannot be published: {rel}")
        size = path.stat().st_size
        if size > 50 * 1024 * 1024:
            raise Error(f"File exceeds this publisher's 50 MiB limit: {rel}")
        total += size
        if static_check.has_secret(path):
            raise Error(f"Possible credential detected in {rel}; inspect locally. Nothing uploaded.")
    if total > 200 * 1024 * 1024:
        raise Error("Source exceeds this publisher's 200 MiB per-publication limit.")
    entry = entry_of(source) if source.is_dir() else source
    title = catalog.title_of(entry) if entry.is_file() and entry.suffix.lower() in {".html", ".htm"} else source.stem
    return source.resolve(), title


def read_config():
    path = CONFIG / "config.json"
    return json.loads(path.read_text()) if path.exists() else {}


def target(args, authenticate=True):
    config = read_config()
    repo = args.repo or config.get("repo")
    if repo and repo.startswith("https://"):
        repo = remote_name(repo) or "INVALID"
    if authenticate:
        for binary in ("gh", "git"):
            if not shutil.which(binary):
                raise Error(f"Install {binary} first; see README.md.")
        if run("gh", "auth", "status", "--hostname", "github.com", check=False).returncode:
            raise Error("GitHub authentication failed. Run gh auth login --hostname github.com, then retry.")
        if not repo or "/" not in repo:
            repo = api("user")["login"] + "/" + (repo or "reports")
    elif not repo or "/" not in repo:
        repo = "AUTHENTICATED_USER/" + (repo or "reports")
    if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repo) or repo.split("/")[1] in {".", ".."}:
        raise Error("Use --repo OWNER/NAME, NAME, or https://github.com/OWNER/NAME.")
    saved_path = config.get("path") if config.get("repo", "").lower() == repo.lower() else None
    path = Path(args.path or saved_path or Path.home() / "projects" / repo.split("/")[0] / repo.split("/")[1]).expanduser().resolve()
    if path == SKILL or SKILL in path.parents or path in SKILL.parents:
        raise Error("Hosting checkout must be separate from the skill directory.")
    origin = git(SKILL, "config", "--get", "remote.origin.url", check=False).stdout
    if remote_name(origin) == repo.lower():
        raise Error("The skill distribution repository cannot host published documents.")
    return repo, path


@contextmanager
def lock(repo):
    if fcntl is None:
        raise Error("Publishing requires macOS, Linux, or WSL; native Windows is unsupported.")
    CONFIG.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(repo.lower().encode()).hexdigest()[:16]
    with (CONFIG / (name + ".lock")).open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Error("Another publish operation for this repository is running.")
        yield


def remote_name(url):
    m = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?", url.strip())
    return m[1].lower() if m else None


def clean(repo):
    if git(repo, "status", "--porcelain", "--untracked-files=all").stdout:
        raise Error(f"Checkout has local changes: {repo}. Preserve or commit them before retrying; no automatic stash.")


def sync(repo):
    result = git(repo, "pull", "--rebase", "origin", "main", check=False)
    # The catalog is generated output. Rebuild only that conflict; never guess
    # how to merge a user's source document. Bound continuation work.
    for _ in range(20):
        if result.returncode == 0:
            return
        conflicts = git(repo, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
        if conflicts != ["index.html"]:
            break
        regenerate(repo)
        git(repo, "add", "--", "index.html")
        result = git(repo, "rebase", "--continue", check=False)
    if result.returncode:
        # Return to the pre-rebase state; the local commit remains recoverable.
        git(repo, "rebase", "--abort", check=False)
        raise Error("Pull/rebase failed; kept local commits. Resolve divergence manually.\n" + result.stderr.strip())


def prepare(name, path):
    # Git identity is the user's configured identity, never a guessed author.
    identity_dir = path if path.exists() else None
    for key in ("user.name", "user.email"):
        if not run("git", "config", "--get", key, cwd=identity_dir, check=False).stdout.strip():
            raise Error(f"Set git config --global {key} before publishing.")
    info = api("repos/" + name, missing_ok=True)
    if info and (info.get("private") or info.get("archived")):
        raise Error("Use a public, unarchived repository. This script never changes repository visibility.")
    if path.exists():
        if not (path / ".git").exists() or Path(git(path, "rev-parse", "--show-toplevel").stdout.strip()).resolve() != path:
            raise Error(f"Target exists and is not its own Git checkout: {path}")
        if remote_name(git(path, "config", "--get", "remote.origin.url").stdout) != name.lower():
            raise Error("Local origin does not match the requested github.com repository.")
        clean(path)
    if info is None:
        log(f"Creating public GitHub repository {name}.")
        run("gh", "repo", "create", name, "--public", "--description", "Public HTML reports and interactive documents")
    else:
        state = api("repos/" + name + "/pages", missing_ok=True)
        if state and (state.get("source") != {"branch": "main", "path": "/"} or state.get("build_type", "legacy") != "legacy"):
            raise Error("Existing Pages configuration differs from main/root. Review it explicitly before changing it.")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        run("gh", "repo", "clone", name, path)
    git(path, "fetch", "origin")
    has_head = git(path, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    if has_head:
        clean(path)
        if git(path, "branch", "--show-current").stdout.strip() != "main":
            raise Error("Existing checkout must be on main; refusing to switch your branch.")
        sync(path)
        if not (path / MARKER).is_file():
            # Adopt only an initialized empty/documentation-only repository.
            tracked = set(git(path, "ls-files").stdout.splitlines())
            if not tracked <= {"README.md", "LICENSE", ".gitignore", ".nojekyll"}:
                raise Error("Existing repository is not managed by publish-html. Choose an empty repository; existing sites are never overwritten.")
        if (path / MARKER).exists() and json.loads((path / MARKER).read_text()).get("version") != 1:
            raise Error("Unsupported publish-html repository format.")
    else:
        git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    # Reject special files throughout the checkout before writing or staging.
    for item in path.rglob("*"):
        rel = item.relative_to(path)
        if ".git" in rel.parts:
            continue
        if item.is_symlink():
            raise Error(f"Site checkout contains a symlink: {rel}")
    return has_head


def scaffold(path, update_generator=False):
    if not (path / MARKER).exists():
        (path / MARKER).write_text('{"version":1}\n')
    (path / ".nojekyll").touch()
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text("# Public reports\n\nPUBLIC STATIC SITE — never add secrets, credentials, or employer/work-confidential data.\n\nDocuments: `YYYY-MM-DD-slug/index.html`, with relative assets alongside. Arbitrary asset folders are supported.\n\nRegenerate the catalog with `python3 scripts/gen-index.py`. Publish through the publish-html skill.\n")
    if not (path / "site.json").exists():
        (path / "site.json").write_text(json.dumps(catalog.DEFAULTS, indent=2)+"\n")
    (path / "scripts").mkdir(exist_ok=True)
    if update_generator or not (path / "scripts/gen-index.py").exists():
        shutil.copyfile(SKILL / "scripts/gen-index.py", path / "scripts/gen-index.py")


def commit_push(path, message, paths):
    git(path, "add", "--", *paths)
    if git(path, "diff", "--cached", "--quiet", check=False).returncode != 0:
        git(path, "commit", "-m", message)
    result = git(path, "push", "-u", "origin", "main", check=False)
    if result.returncode == 0:
        return
    if not any(s in result.stderr.lower() for s in ("non-fast-forward", "fetch first")):
        raise Error("Push failed; the commit remains local.\n" + result.stderr.strip())
    log("Remote advanced; pulling with rebase and retrying once.")
    sync(path)
    regenerate(path)
    git(path, "add", "--", "index.html")
    if git(path, "diff", "--cached", "--quiet", check=False).returncode:
        git(path, "commit", "-m", "Refresh document catalog after rebase")
    git(path, "push", "-u", "origin", "main")


def pages(name):
    endpoint = "repos/" + name + "/pages"
    state = api(endpoint, missing_ok=True)
    source = {"branch": "main", "path": "/"}
    if state is None:
        try:
            api(endpoint, "POST", {"build_type": "legacy", "source": source})
        except Error:
            # POST may have succeeded despite a lost response. Reconcile before
            # considering another mutation; never blindly replay a POST.
            recovered = api(endpoint, missing_ok=True)
            if recovered is None or recovered.get("source") != source or recovered.get("build_type", "legacy") != "legacy":
                raise
    elif state.get("source") != source or state.get("build_type", "legacy") != "legacy":
        raise Error("Existing Pages configuration differs from main/root. Review it explicitly before changing it.")
    state = api(endpoint)
    url = state.get("html_url")
    if not url or urlparse(url).scheme not in {"https", "http"}:
        raise Error("GitHub did not return a valid Pages URL.")
    return url.rstrip("/") + "/"


def verify(url, expected, timeout):
    deadline = time.monotonic() + timeout
    digest = hashlib.sha256(expected).hexdigest()
    log(f"Waiting for deployed content: {url}")
    while True:
        try:
            request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "publish-html"})
            with urlopen(request, timeout=min(15, max(1, deadline - time.monotonic()))) as response:
                if response.status == 200 and hashlib.sha256(response.read()).hexdigest() == digest:
                    log("Verified HTTP 200 and exact published HTML/asset bytes.")
                    return
        except (URLError, TimeoutError, OSError):
            pass
        if time.monotonic() >= deadline:
            raise Error(f"Pushed successfully, but live content was not verified within {timeout}s. Check Pages build status; retry safely. Expected URL: {url}")
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def asset_index(folder, title):
    entries = []
    for file in sorted(folder.rglob("*")):
        if file.is_file():
            rel = file.relative_to(folder).as_posix()
            entries.append(f'<li><a href="{quote(rel)}">{html.escape(rel)}</a></li>')
    (folder / "index.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>:root{color-scheme:light dark}body{max-width:800px;margin:60px auto;padding:24px;font:18px/1.7 system-ui}a{overflow-wrap:anywhere}li{margin:12px 0}</style><h1>' + html.escape(title) + '</h1><ul>' + "".join(entries) + '</ul></html>', encoding="utf-8")


@contextmanager
def stage_source(value):
    # Copy before network activity. Preserve symlinks so the staged scan can refuse
    # a source changed to a symlink during copying rather than dereferencing it.
    source, title = inspect_source(value)
    with tempfile.TemporaryDirectory(prefix="publish-html-stage-") as tmp:
        staged = Path(tmp) / "document"
        copy_source(source, staged, title)
        _, title = inspect_source(staged)
        findings = static_check.check(staged)
        errors = [x for x in findings if x["level"] == "error"]
        for item in findings:
            log(f"{item['level']} {item['code']} {item['file']}: {item['message']}")
        if errors:
            raise Error("Static preflight failed; nothing uploaded.")
        yield source, staged, title, tree_bytes(staged)


def replace_tree(staged, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".publish-swap-") as tmp:
        incoming, backup = Path(tmp) / "incoming", Path(tmp) / "backup"
        shutil.copytree(staged, incoming)
        had_old = destination.exists()
        if had_old: destination.rename(backup)
        try:
            incoming.rename(destination)
        except BaseException:
            if had_old: backup.rename(destination)
            raise


def expected_url(name):
    owner, repo = name.split("/")
    return f"https://{owner.lower()}.github.io/" + ("" if repo.lower() == owner.lower()+".github.io" else quote(repo)+"/")


def deployed_base(name, path, folder=""):
    # A pushed commit is public even when Pages setup fails. Preserve the target
    # before attempting Pages and report that partial success explicitly.
    save_config(name, path)
    try:
        return pages(name)
    except Error as exc:
        raise Error(f"Pushed successfully; Pages configuration failed. Target saved. Expected URL (deployment unverified): {expected_url(name)}{folder}\n{exc}") from exc


def verify_tree(url, staged, timeout):
    deadline = time.monotonic() + timeout
    for relative in sorted(tree_bytes(staged)):
        remaining = max(1, deadline - time.monotonic())
        verify(url + quote(relative, safe="/"), (staged / relative).read_bytes(), remaining)
    log("Verified every file in the staged manifest.")


def document_target(path, title, folder=None, document=None):
    """Find the original folder across dates; an explicit ID also survives title edits."""
    identity = document or slug(title)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", identity):
        raise Error("--document must be a stable lowercase ID using letters, digits, hyphens or underscores (max 96).")
    marker = path / MARKER
    state = json.loads(marker.read_text()) if marker.exists() else {}
    documents = state.get("documents", {})
    if not isinstance(documents, dict):
        raise Error("Invalid document registry in " + MARKER)
    registered = documents.get(identity)
    if registered and folder and registered["folder"] != folder and document:
        raise Error(f"Document {identity} is registered at {registered['folder']}; reuse that folder or choose a new --document ID.")
    selected = folder or (registered["folder"] if registered else f"{dt.date.today().isoformat()}-{slug(title)}")
    return identity, safe_folder(selected)


def register_document(path, identity, folder, title):
    marker = path / MARKER
    state = json.loads(marker.read_text())
    documents = state.setdefault("documents", {})
    # Explicitly editing an old unregistered folder can introduce a title-derived
    # ID. Keep one current registry entry per document directory, not aliases.
    for key in list(documents):
        if key != identity and documents[key]["folder"] == folder:
            del documents[key]
    documents[identity] = {"folder": folder, "title": title}
    marker.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def publish(args):
    with stage_source(args.source) as (source, staged, title, manifest):
        if args.dry_run:
            name, path = target(args, authenticate=False)
            identity, folder = document_target(path, title, args.folder, args.document)
            print(json.dumps({"repo": name, "checkout": str(path), "source": str(source), "folder": folder,
                              "document": identity,
                              "manifest": manifest, "replace_folder": args.replace, "public": True, "network_requests": False}, indent=2))
            return
        name, path = target(args)
        if source == path or path in source.parents or source in path.parents:
            raise Error("Stage source outside the site checkout, so pulling cannot change the publication input.")
        with lock(name):
            prepare(name, path)
            identity, folder = document_target(path, title, args.folder, args.document)
            # Optional comments are applied to the staged snapshot, never source files.
            import comments
            comments.decorate(staged, path, name, identity)
            manifest = tree_bytes(staged)
            destination = path / folder
            if destination.exists() and not args.replace and manifest != tree_bytes(destination):
                raise Error(f"Destination exists with different contents: {folder}. Use --replace to update that document.")
            scaffold(path, args.update_generator)
            replace_tree(staged, destination)
            register_document(path, identity, folder, title)
            regenerate(path)
            commit_push(path, f"Publish {folder}: {title[:100]}", [folder, MARKER, ".nojekyll", "README.md", "scripts/gen-index.py", "index.html", "site.json"])
            # Refuse to claim our bytes deployed if a concurrent source merge changed them.
            if tree_bytes(destination) != manifest:
                save_config(name, path)
                raise Error("Pushed successfully, but merged document differs from staged manifest; deployment unverified.")
            base = deployed_base(name, path, quote(folder,safe="/")+"/")
            url = base + quote(folder, safe="/") + "/"
            if not args.no_wait:
                verify_tree(url, staged, args.timeout)
                verify(base, (path / "index.html").read_bytes(), args.timeout)
            else:
                log("Pushed; live deployment was not verified (--no-wait).")
            revision = git(path, "rev-parse", "HEAD").stdout.strip()
            log(f"Version: https://github.com/{name}/commit/{revision}")
            print(url)


def tree_bytes(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob("*") if p.is_file()}


def entry_of(directory):
    entries = [p for p in directory.iterdir() if p.name.lower() in {"index.html", "index.htm"}]
    if len(entries) > 1:
        raise Error("Ambiguous entry pages: keep only one index.html or index.htm.")
    return entries[0] if entries else directory / "index.html"


def regenerate(path):
    # Execute the site's explicitly user-owned generator, never replace it silently.
    run(sys.executable, path / "scripts/gen-index.py", path)


def copy_source(source, target_dir, title):
    if source.is_dir():
        shutil.copytree(source, target_dir, symlinks=True)
    else:
        target_dir.mkdir(parents=True)
        filename = "index.html" if source.suffix.lower() in {".html", ".htm"} else source.name
        shutil.copyfile(source, target_dir / filename)
    entry = entry_of(target_dir)
    if entry.exists():
        if entry.name != "index.html": entry.rename(target_dir / "index.html")
    else:
        asset_index(target_dir, title)


def save_config(name, path):
    with tempfile.NamedTemporaryFile(mode="w", dir=CONFIG, delete=False) as handle:
        json.dump({"repo": name, "path": str(path)}, handle, indent=2)
        handle.write("\n")
    Path(handle.name).replace(CONFIG / "config.json")


def setup(args):
    if args.dry_run:
        name, path = target(args, authenticate=False)
        print(json.dumps({"repo":name,"checkout":str(path),"public":True,"source":{"branch":"main","path":"/"},"network_requests":False},indent=2))
        return
    name, path = target(args)
    with lock(name):
        prepare(name, path)
        scaffold(path, args.update_generator)
        regenerate(path)
        commit_push(path, "Set up public HTML publishing", [MARKER, ".nojekyll", "README.md", "scripts/gen-index.py", "index.html", "site.json"])
        url = deployed_base(name, path)
        if not args.no_wait:
            verify(url, (path / "index.html").read_bytes(), args.timeout)
        else:
            log("Pushed; live deployment was not verified (--no-wait).")
        print(url)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for verb in ("setup", "publish"):
        s = sub.add_parser(verb)
        s.add_argument("--repo", help="OWNER/NAME, GitHub URL, or NAME; defaults to authenticated user/reports")
        s.add_argument("--path", help="Dedicated checkout; defaults to ~/projects/OWNER/NAME")
        s.add_argument("--timeout", type=int, default=180, help="Deployment verification seconds (default: 180)")
        s.add_argument("--dry-run", action="store_true", help="Show plan without network or checkout/config mutations; publish uses temporary staging")
        s.add_argument("--update-generator", action="store_true", help="Explicitly replace the site catalog generator with this skill version")
        s.add_argument("--no-wait", action="store_true", help="Skip live verification; report deployment as unverified")
        if verb == "publish":
            s.add_argument("source", help="HTML file, asset file, or directory")
            s.add_argument("folder", nargs="?")
            s.add_argument("--document", help="Stable document ID; reuses its registered folder across dates and title changes")
            s.add_argument("--replace", action="store_true", help="Replace an existing document folder, including obsolete assets")
    return p


def main():
    args = parser().parse_args()
    try:
        if args.timeout < 1:
            raise Error("--timeout must be at least 1 second.")
        (publish if args.command == "publish" else setup)(args)
    except (Error, OSError, ValueError) as exc:
        log(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
