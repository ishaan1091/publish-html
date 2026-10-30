#!/usr/bin/env python3
"""Serve a document locally; never publish or expose it on the LAN."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("directory", type=Path)
p.add_argument("--port", type=int, default=8000)
p.add_argument("--base", default="/", help="Simulate a Pages project subpath, e.g. /reports/")
args = p.parse_args()
root = args.directory.resolve(strict=True)
if not root.is_dir():
    p.error("directory must be a directory")
if any(x.is_symlink() for x in root.rglob("*")):
    p.error("preview directory must not contain symlinks")
base = "/" + args.base.strip("/") + "/" if args.base.strip("/") else "/"
if any(part in {".", ".."} for part in base.split("/")) or any(x in base for x in "?#\\"):
    p.error("base must be a URL path without traversal, query, or fragment")

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not urlsplit(self.path).path.startswith(base):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        if not urlsplit(self.path).path.startswith(base):
            self.send_error(404)
            return
        super().do_HEAD()

    def translate_path(self, path):
        return super().translate_path("/" + path[len(base):])

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

with ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(root))) as server:
    print(f"http://127.0.0.1:{server.server_port}{base}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
