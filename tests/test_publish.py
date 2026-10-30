"""Offline verification: real git repos, fake gh, local deployment HTTP server."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


pub = module("publisher", ROOT / "scripts/publish.py")
installer = module("installer", ROOT / "scripts/install.py")

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
a=sys.argv[1:]; base=pathlib.Path(os.environ['FAKE_GH_ROOT']); remote=base/'remote.git'
with (base/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\n')
def out(x): print(json.dumps(x)); sys.exit(0)
def missing(): print('gh: Not Found (HTTP 404)',file=sys.stderr); sys.exit(1)
if a[:2]==['auth','status']: sys.exit(1 if os.environ.get('FAKE_AUTH_FAIL') else 0)
if a[:2]==['repo','create']:
    subprocess.run(['git','init','--bare','--initial-branch=main',str(remote)],check=True,capture_output=True); sys.exit(0)
if a[:2]==['repo','clone']:
    sys.exit(subprocess.run(['git','clone','https://github.com/'+a[2]+'.git',a[3]],capture_output=True).returncode)
if a[0]=='api':
    endpoint=a[1]; method=a[a.index('--method')+1]
    if endpoint=='user': out({'login':'reader'})
    if endpoint=='repos/reader/reports':
        if os.environ.get('FAKE_API_403'): print('gh: Forbidden (HTTP 403)',file=sys.stderr); sys.exit(1)
        if not remote.exists(): missing()
        out({'private':bool(os.environ.get('FAKE_PRIVATE')), 'archived':False})
    if endpoint=='repos/reader/reports/pages':
        state=base/'pages.json'
        if method=='POST':
            body=json.load(sys.stdin); body['html_url']=os.environ['FAKE_SITE_URL']; state.write_text(json.dumps(body)); out(body)
        if not state.exists(): missing()
        out(json.loads(state.read_text()))
raise SystemExit('Unsupported fake gh command: '+repr(a))
'''


class Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(FAKE_GH)
        (self.bin / "gh").chmod(0o755)
        self.remote = self.base / "remote.git"
        config = self.base / "gitconfig"
        config.write_text(f'[user]\n name = Test Publisher\n email = test@example.invalid\n[url "{self.remote.as_uri()}"]\n insteadOf = https://github.com/reader/reports.git\n[protocol "file"]\n allow = always\n')
        self.env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                    "GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "0",
                    "FAKE_GH_ROOT": str(self.base), "XDG_CONFIG_HOME": str(self.base / "config")}
        remote = self.remote
        env = self.env
        blocked = self.blocked = set()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                file = self.path.removeprefix("/reports/").split("?")[0]
                if not file or file.endswith("/"):
                    file += "index.html"
                result = subprocess.run(["git", "--git-dir", str(remote), "show", "main:" + file], capture_output=True, env=env)
                if file in blocked:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200 if result.returncode == 0 else 404)
                self.end_headers()
                self.wfile.write(result.stdout)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.env["FAKE_SITE_URL"] = f"http://127.0.0.1:{self.server.server_port}/reports/"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.checkout = self.base / "checkout"
        self.source = self.base / "source"
        self.source.mkdir()
        (self.source / "index.html").write_text('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>A report &amp; a question</title><p>Public synthetic example.</p></html>')
        (self.source / "data.csv").write_text('name,value\na,1\n')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def command(self, verb="publish", *extra, success=True, env=None):
        args = [sys.executable, str(ROOT / "scripts/publish.py"), verb]
        if verb == "publish":
            args += [str(self.source), "2026-10-29-example"]
        args += ["--repo", "reader/reports", "--path", str(self.checkout), "--timeout", "2", *extra]
        result = subprocess.run(args, env={**self.env, **(env or {})}, text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def git(self, *args, cwd=None, success=True):
        result = subprocess.run(["git", *args], cwd=cwd or self.checkout, env=self.env, text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_setup_publish_replay_update_and_live_bytes(self):
        setup = self.command("setup")
        self.assertIn("Verified HTTP 200 and exact", setup.stderr)
        initial = self.git("rev-parse", "HEAD")
        self.command("setup")
        self.assertEqual(initial, self.git("rev-parse", "HEAD"))
        result = self.command()
        self.assertEqual(result.stdout.strip(), self.env["FAKE_SITE_URL"] + "2026-10-29-example/")
        self.assertIn("Verified HTTP 200 and exact", result.stderr)
        head = self.git("rev-parse", "HEAD")
        self.command()
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("status", "--porcelain"), "")
        (self.source / "index.html").write_text('<html lang="en"><meta name="viewport" content="width=device-width"><title>Updated</title><p>Changed example.</p></html>')
        (self.source / "data.csv").unlink()
        rejected = self.command(success=False)
        self.assertIn("--replace", rejected.stderr)
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        self.command("publish", "--replace")
        self.assertFalse((self.checkout / "2026-10-29-example/data.csv").exists())
        self.assertIn("Updated", (self.checkout / "index.html").read_text())
        self.assertNotEqual(head, self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_first_publish_bootstraps_missing_repo(self):
        self.command()
        config = json.loads((self.base / "config/publish-html/config.json").read_text())
        self.assertEqual(config, {"repo":"reader/reports", "path":str(self.checkout.resolve())})
        calls = [json.loads(s) for s in (self.base / "calls.jsonl").read_text().splitlines()]
        self.assertIn(["repo", "create", "reader/reports", "--public", "--description", "Public HTML reports and interactive documents"], calls)
        self.assertEqual(json.loads((self.base / "pages.json").read_text())["source"], {"branch":"main","path":"/"})

    def test_auth_and_api_failure_do_not_create(self):
        failure = self.command(success=False, env={"FAKE_AUTH_FAIL":"1"})
        self.assertIn("authentication failed", failure.stderr)
        self.assertFalse(self.remote.exists())
        failure = self.command(success=False, env={"FAKE_API_403":"1"})
        self.assertIn("HTTP 403", failure.stderr)
        self.assertFalse(self.remote.exists())

    def test_dirty_checkout_and_private_repo_stop(self):
        self.command()
        (self.checkout / "personal.txt").write_text("keep this")
        failure = self.command(success=False)
        self.assertIn("local changes", failure.stderr)
        self.assertEqual((self.checkout / "personal.txt").read_text(), "keep this")
        failure = self.command(success=False, env={"FAKE_PRIVATE":"1"})
        self.assertIn("public, unarchived", failure.stderr)

    def test_existing_pages_configuration_not_overwritten(self):
        self.command()
        state = json.loads((self.base / "pages.json").read_text())
        state["source"] = {"branch":"gh-pages", "path":"/"}
        (self.base / "pages.json").write_text(json.dumps(state))
        failure = self.command(success=False)
        self.assertIn("configuration differs", failure.stderr)
        self.assertEqual(json.loads((self.base / "pages.json").read_text()), state)

    def test_push_rejection_merges_generated_catalog_and_retries(self):
        self.command()
        other = self.base / "other"
        self.git("clone", str(self.remote), str(other))
        (other / "2026-10-30-other").mkdir()
        (other / "2026-10-30-other/index.html").write_text('<title>Other document</title>')
        pub.catalog.generate(other)
        self.git("add", ".", cwd=other)
        self.git("commit", "-m", "Other publication", cwd=other)
        self.git("push", "origin", "main", cwd=other)
        (self.checkout / "2026-10-31-local").mkdir()
        (self.checkout / "2026-10-31-local/index.html").write_text('<title>Local document</title>')
        pub.catalog.generate(self.checkout)
        with patch.dict(os.environ, self.env):
            pub.commit_push(self.checkout, "Local publication", ["2026-10-31-local", "index.html"])
        catalog = (self.checkout / "index.html").read_text()
        self.assertIn("Other document", catalog)
        self.assertIn("Local document", catalog)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", "origin/main"))

    def test_real_content_conflict_aborts_and_preserves_local_commit(self):
        self.command()
        other = self.base / "other"
        self.git("clone", str(self.remote), str(other))
        file = "2026-10-29-example/index.html"
        (other / file).write_text("remote edit")
        self.git("add", file, cwd=other)
        self.git("commit", "-m", "Remote edit", cwd=other)
        self.git("push", "origin", "main", cwd=other)
        (self.checkout / file).write_text("local edit")
        with patch.dict(os.environ, self.env), self.assertRaises(pub.Error):
            pub.commit_push(self.checkout, "Local edit", [file])
        self.assertEqual((self.checkout / file).read_text(), "local edit")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "Local edit")

    def test_publishes_staged_bytes_after_source_changes(self):
        original = (self.source / "index.html").read_bytes()
        prepare = pub.prepare
        def mutate_then_prepare(name, path):
            (self.source / "index.html").write_text("source changed after staging")
            return prepare(name, path)
        args = pub.parser().parse_args(["publish", str(self.source), "2026-10-29-example", "--repo", "reader/reports", "--path", str(self.checkout), "--timeout", "2"])
        with patch.dict(os.environ,self.env), patch.object(pub,"CONFIG",self.base/"config/publish-html"), patch.object(pub,"prepare",mutate_then_prepare), redirect_stdout(io.StringIO()):
            pub.publish(args)
        self.assertEqual((self.checkout/"2026-10-29-example/index.html").read_bytes(),original)

    def test_missing_deployed_asset_is_partial_success_with_saved_target(self):
        self.blocked.add("2026-10-29-example/data.csv")
        failure = self.command(success=False)
        self.assertIn("Pushed successfully",failure.stderr)
        self.assertIn("data.csv",failure.stderr)
        self.assertTrue((self.base/"config/publish-html/config.json").exists())
        self.assertTrue(self.git("rev-parse","origin/main"))

    def test_ignored_file_and_custom_generator_preserved(self):
        self.command()
        (self.checkout/".gitignore").write_text(".DS_Store\n")
        generator=self.checkout/"scripts/gen-index.py"
        generator.write_text(generator.read_text()+"\n# User customization\n")
        self.git("add",".");self.git("commit","-m","Customize generator and ignores");self.git("push","origin","main")
        (self.checkout/".DS_Store").write_bytes(b"ignored")
        self.command()
        self.assertIn("User customization",generator.read_text())
        self.command("publish","--update-generator")
        self.assertNotIn("User customization",generator.read_text())

    def test_preflight_and_dry_run_do_not_contact_github(self):
        (self.source/"index.html").write_text('<html lang="en"><meta name="viewport"><title>x</title><img alt="x" src="missing.png"></html>')
        failed=self.command(success=False)
        self.assertIn("E001",failed.stderr)
        self.assertFalse((self.base/"calls.jsonl").exists())
        (self.source/"index.html").write_text('<html lang="en"><meta name="viewport"><title>x</title></html>')
        result=self.command("publish","--dry-run")
        self.assertIn("data.csv",json.loads(result.stdout)["manifest"])
        self.assertFalse((self.base/"calls.jsonl").exists())
        self.assertFalse(self.checkout.exists())


    def test_automatic_registration_reuse_and_git_versions(self):
        def publish_registered(*flags):
            result = subprocess.run([sys.executable, str(ROOT / "scripts/publish.py"), "publish", str(self.source), "--document", "stable-report", "--timeout", "2", *flags], env=self.env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result
        # No --repo: discover authenticated owner and bootstrap reports.
        first = publish_registered("--path", str(self.checkout))
        before = self.git("rev-parse", "HEAD")
        marker = json.loads((self.checkout / pub.MARKER).read_text())
        folder = marker["documents"]["stable-report"]["folder"]
        original = (self.checkout / folder / "index.html").read_bytes()
        self.assertEqual(first.stdout.strip(), self.env["FAKE_SITE_URL"] + folder + "/")
        # No --path/--repo on any following invocation: use saved registration.
        replay = publish_registered()
        self.assertEqual(before, self.git("rev-parse", "HEAD"))
        self.assertEqual(first.stdout, replay.stdout)
        (self.source / "index.html").write_text('<html lang="en"><meta name="viewport"><title>Changed title</title><p>Revision two</p></html>')
        updated = publish_registered("--replace")
        self.assertEqual(first.stdout, updated.stdout)
        self.assertNotEqual(before, self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("show", before + ":" + folder + "/index.html"), original.decode().strip())
        self.assertEqual(len(json.loads((self.checkout / pub.MARKER).read_text())["documents"]), 1)
        self.assertIn("Version: https://github.com/reader/reports/commit/", updated.stderr)
        # Registration and document identity survive checkout removal/recloning.
        import shutil
        shutil.rmtree(self.checkout)
        restored = publish_registered()
        self.assertEqual(restored.stdout, first.stdout)
        calls = [json.loads(line) for line in (self.base / "calls.jsonl").read_text().splitlines()]
        self.assertEqual(sum(call[:2] == ["repo", "create"] for call in calls), 1)

    def test_separate_documents_get_separate_folders_and_survive_setup(self):
        self.command("publish", "--document", "first-document")
        first_folder = "2026-10-29-example"
        (self.source / "index.html").write_text('<html lang="en"><meta name="viewport"><title>A second report</title></html>')
        result = subprocess.run([sys.executable, str(ROOT / "scripts/publish.py"), "publish", str(self.source), "--document", "second-document", "--timeout", "2"], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = json.loads((self.checkout / pub.MARKER).read_text())["documents"]
        self.assertEqual(docs["first-document"]["folder"], first_folder)
        self.assertNotEqual(docs["second-document"]["folder"], first_folder)
        self.assertTrue((self.checkout / first_folder / "data.csv").exists())
        self.command("setup")
        self.assertEqual(json.loads((self.checkout / pub.MARKER).read_text())["documents"], docs)



class Local(unittest.TestCase):
    def test_index_sorting_escaping_nested_undated_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder, title in [("2026-01-01-first", "Old"), ("nested/2026-10-29-new", "<script>"), ("archive", "Undated")]:
                (root / folder).mkdir(parents=True)
                (root / folder / "index.html").write_text("<title>" + title.replace("<", "&lt;").replace(">", "&gt;") + "</title>")
            pub.catalog.generate(root)
            first = (root / "index.html").read_text()
            pub.catalog.generate(root)
            self.assertEqual(first, (root / "index.html").read_text())
            self.assertLess(first.index('nested/2026-10-29-new/'), first.index('2026-01-01-first/'))
            self.assertLess(first.index('2026-01-01-first/'), first.index('archive/'))
            self.assertIn("&lt;script&gt;", first)
            self.assertNotIn("<script>", first)

    def test_source_guardrails_and_asset_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "data.csv"
            source.write_text("a,b\n1,2")
            path, title = pub.inspect_source(source)
            pub.copy_source(path, root / "output", title)
            self.assertIn("data.csv", (root / "output/index.html").read_text())
            secret = root / "private.html"
            secret.write_text("-----BEGIN PRIVATE KEY-----")
            with self.assertRaises(pub.Error): pub.inspect_source(secret)
            link = root / "link"
            link.symlink_to(source)
            with self.assertRaises(pub.Error): pub.inspect_source(link)
            for invalid in ["../escape", "/absolute", ".git", "scripts/report", "index.html", "README.md/sub", "a//b", "a/./b", "a b"]:
                with self.assertRaises(pub.Error): pub.safe_folder(invalid)
            self.assertEqual(pub.safe_folder("archive/2026-10-29-report"), "archive/2026-10-29-report")

    def test_install_idempotent_preserves_instructions_single_implementation(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            agents = home / ".codex/AGENTS.md"
            agents.parent.mkdir()
            original = "# Existing preferences\n\nKeep this instruction.\n"
            agents.write_text(original)
            with redirect_stdout(io.StringIO()):
                installer.install("both", home)
                once = agents.read_text()
                installer.install("both", home)
            self.assertEqual(agents.read_text(), once)
            self.assertTrue(once.startswith(original))
            self.assertEqual(once.count(installer.START), 1)
            self.assertEqual((home / ".claude/skills/publish-html").resolve(), ROOT)
            self.assertEqual((home / ".codex/skills/publish-html").resolve(), ROOT)
            self.assertEqual(agents.with_name("AGENTS.md.before-publish-html").read_text(), original)

    def test_install_refuses_existing_different_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".codex/skills/publish-html").mkdir(parents=True)
            with self.assertRaises(ValueError): installer.install("both", home)
            self.assertFalse((home / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
