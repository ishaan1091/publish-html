#!/usr/bin/env python3
"""Regenerate a static document catalog; Python standard library only."""
import argparse
import datetime as dt
import html
import json
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import quote


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.parts.append(data)


def title_of(path):
    parser = TitleParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return " ".join("".join(parser.parts).split()) or path.parent.name


DEFAULTS = {"title":"Reports", "description":"Public reports and interactive documents.", "lang":"en", "accent":"#245c45", "nav":"Documents", "author":"", "footer":"Public reports and documents.", "dark_accent":"#9ad4af", "collection":"Collection", "document_singular":"document", "document_plural":"documents", "undated":"Undated", "empty":"No documents yet."}


def site_config(root):
    try:
        data = json.loads((root / "site.json").read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict): data = {}
    result = {k: data.get(k) if isinstance(data.get(k), str) else v for k,v in DEFAULTS.items()}
    for key in ("accent", "dark_accent"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", result[key]): result[key] = DEFAULTS[key]
    return result


def generate(root):
    root = Path(root).resolve()
    config = site_config(root)
    documents = []
    selected = set()
    for path in sorted(root.rglob("index.html"), key=lambda p: (len(p.parts), str(p))):
        rel = path.relative_to(root)
        if len(rel.parts) == 1 or any(p.startswith(".") or p in {"scripts", "node_modules"} for p in rel.parts):
            continue
        if any(p.is_symlink() for p in (path, *path.parents)):
            continue
        if any(parent in selected for parent in path.parents):
            continue
        selected.add(path.parent)
        folder = rel.parent.as_posix()
        match = re.search(r"(?:^|/)(\d{4}-\d{2}-\d{2})-", folder)
        date = ""
        if match:
            try:
                date = dt.date.fromisoformat(match[1]).isoformat()
            except ValueError:
                pass
        documents.append((date, folder, title_of(path)))
    documents.sort(key=lambda d: (d[0], d[1]), reverse=True)
    rows = []
    for date, folder, title in documents:
        date_label = f'<time datetime="{date}">{date}</time>' if date else html.escape(config["undated"])
        rows.append(f'''<li><a href="{quote(folder, safe='/')}/"><div class="meta">{date_label}<span aria-hidden="true">↗</span></div><h2>{html.escape(title)}</h2><code>{html.escape(folder)}/</code></a></li>''')
    body = "\n".join(rows) or '<li class="empty">'+html.escape(config['empty'])+'</li>'
    output = '''<!doctype html>
<html lang="SITE_LANG"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="description" content="SITE_DESCRIPTION"><title>SITE_TITLE</title>
<style>
:root{color-scheme:light dark;--bg:#f4f3ee;--ink:#182c29;--muted:#586b65;--line:#c9d4cb;--paper:#fffef9;--accent:SITE_ACCENT}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:64px 24px 80px}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:.73rem;font-weight:750;color:var(--accent)}header{max-width:730px;margin-bottom:48px}h1{font:500 clamp(3rem,8vw,5.5rem)/1.04 Georgia,serif;letter-spacing:-.045em;margin:20px 0}header p{font-size:1.12rem;color:var(--muted)}.rule{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding-top:18px;margin-bottom:24px;color:var(--muted);font-size:.85rem}ul{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:18px;padding:0;list-style:none}li a{display:block;height:100%;padding:26px;background:var(--paper);border:1px solid var(--line);border-radius:14px;text-decoration:none;color:inherit}li a:hover,li a:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.meta{display:flex;justify-content:space-between;font-size:.8rem;color:var(--accent)}h2{font:500 1.65rem/1.2 Georgia,serif;margin:24px 0 16px}code{font-size:.74rem;overflow-wrap:anywhere;color:var(--muted)}.empty{padding:40px;border:1px dashed var(--line);border-radius:14px}footer{margin-top:55px;font-size:.8rem;color:var(--muted)}
@media(prefers-color-scheme:dark){:root{--bg:#14221f;--ink:#edf1e8;--muted:#a8b9af;--line:#3b4e45;--paper:#1d3029;--accent:SITE_DARK_ACCENT}}
@media(max-width:550px){main{padding-top:36px}}
</style></head><body><main><header><div class="eyebrow">SITE_NAV</div><h1>SITE_TITLE</h1><p>SITE_DESCRIPTION</p></header>
<div class="rule"><span>SITE_COLLECTION</span><span>COUNT LABEL</span></div><ul>ROWS</ul><footer>SITE_FOOTER SITE_AUTHOR</footer></main></body></html>
'''
    values = {"COUNT":str(len(documents)), "LABEL":html.escape(config["document_singular"] if len(documents)==1 else config["document_plural"]), "ROWS":body}
    values.update({"SITE_"+key.upper():html.escape(value,quote=True) for key,value in config.items()})
    output = re.sub(r'SITE_[A-Z_]+|COUNT|LABEL|ROWS', lambda m: values[m[0]], output)
    (root / "index.html").write_text(output, encoding="utf-8")
    return len(documents)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args()
    print(f"Indexed {generate(args.root)} documents.")
