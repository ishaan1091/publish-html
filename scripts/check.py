#!/usr/bin/env python3
"""Check static documents and local asset paths without executing page code."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

# High-confidence tripwires only. Never include matched bytes in diagnostics.
SECRET = re.compile(rb'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----|-----BEGIN PGP PRIVATE KEY BLOCK-----|(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{35}|xox[baprs]-[A-Za-z0-9-]{20,}|sk_live_[A-Za-z0-9]{20,}')


def has_secret(path):
    tail = b''
    with path.open('rb') as stream:
        while True:
            block = stream.read(65536)
            if not block:
                return False
            if SECRET.search(tail + block):
                return True
            tail = block[-512:]


def css_refs(text):
    return re.findall(r'url\(\s*[\"\']?([^\"\')]+)[\"\']?\s*\)', text, re.I) + re.findall(r'@import\s+[\"\']([^\"\']+)', text, re.I)


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.refs = []
        self.ids = []
        self.problems = []
        self.lang = self.viewport = self.title = self.description = False
        self.style = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'): self.ids.append(a['id'])
        if tag == 'html': self.lang = bool(a.get('lang'))
        if tag == 'title': self.title = True
        if tag == 'meta' and a.get('name', '').lower() == 'viewport': self.viewport = True
        if tag == 'meta' and a.get('name', '').lower() == 'description': self.description = True
        if tag == 'img' and 'alt' not in a: self.problems.append(('error','E005','Image is missing alt.'))
        if a.get('target') == '_blank' and 'noopener' not in a.get('rel','').split():
            self.problems.append(('warning','W007','External window should declare rel=noopener.'))
        for attr in ('href','src','poster'):
            if a.get(attr): self.refs.append(a[attr])
        if a.get('srcset') and not a['srcset'].lstrip().startswith('data:'):
            self.refs.extend(item.strip().split()[0] for item in a['srcset'].split(',') if item.strip())
        self.refs.extend(css_refs(a.get('style','')))
        if tag == 'style': self.style = True

    def handle_endtag(self, tag):
        if tag == 'style': self.style = False

    def handle_data(self, data):
        if self.style: self.refs.extend(css_refs(data))


def exact_path(root, relative):
    current = root
    for part in relative.parts:
        if part not in {p.name for p in current.iterdir()}:
            return False
        current /= part
        if not current.exists(): return False
    return True


def check(root):
    root = Path(root).resolve()
    if not root.is_dir(): raise ValueError('Pass a document directory.')
    findings = []
    def add(path, level, code, message):
        findings.append({'file':str(path.relative_to(root)), 'level':level, 'code':code, 'message':message})
    pages = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            add(path,'error','E013','Symlinks are not publishable.');continue
        if not path.is_file(): continue
        if has_secret(path): add(path,'error','E011','Possible credential detected; inspect locally. No matched value is logged.')
        if path.suffix.lower() in {'.html','.htm'}:
            page = Page(path.read_text(encoding='utf-8', errors='replace'));pages[path] = page
            for level,code,msg in page.problems: add(path,level,code,msg)
            for valid,code,msg in [(page.lang,'E006','Missing html lang.'),(page.viewport,'E007','Missing viewport meta.'),(page.title,'E008','Missing title.')]:
                if not valid: add(path,'error',code,msg)
            if not page.description: add(path,'warning','W005','Missing meta description.')
            for ident,count in Counter(page.ids).items():
                if count > 1: add(path,'error','E004',f'Duplicate id: {ident}')
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink(): continue
        refs = pages[path].refs if path in pages else css_refs(path.read_text(encoding='utf-8',errors='replace')) if path.suffix.lower()=='.css' else []
        for ref in refs:
            u = urlsplit(ref.strip())
            if u.scheme or u.netloc:
                if ref.startswith('//'): add(path,'warning','W002','Protocol-relative reference: '+ref)
                elif u.scheme == 'http': add(path,'warning','W001','Unencrypted external reference: '+ref)
                continue
            if u.path.startswith('/'):
                add(path,'error','E003','Root-absolute path breaks project subpaths: '+ref);continue
            target = (path.parent / unquote(u.path)).resolve() if u.path else path
            if not target.is_relative_to(root):
                add(path,'error','E001','Reference escapes the document folder: '+ref);continue
            if target.is_dir(): target /= 'index.html'
            if not target.exists():
                add(path,'error','E001','Missing local reference: '+ref);continue
            if not exact_path(root,target.relative_to(root)):
                add(path,'error','E002','Reference has incorrect filename case: '+ref);continue
            if u.fragment and target in pages and unquote(u.fragment) not in pages[target].ids:
                add(path,'error','E009','Missing fragment target: '+ref)
    return findings


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('path',type=Path);p.add_argument('--json',action='store_true');a=p.parse_args()
    try:
        result=check(a.path)
        if a.json: print(json.dumps(result,indent=2))
        else:
            for item in result: print(f"{item['level']} {item['code']} {item['file']}: {item['message']}")
            if not result: print('No static findings.')
        raise SystemExit(int(any(x['level']=='error' for x in result)))
    except (ValueError,OSError) as exc: p.exit(2,str(exc)+'\n')
