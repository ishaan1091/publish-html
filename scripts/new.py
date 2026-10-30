#!/usr/bin/env python3
"""Create a local interactive HTML starting point without publishing."""
import argparse
import html
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("destination", type=Path, help="New directory to create")
p.add_argument("--title", default="A small change. A clearer picture.")
p.add_argument("--type", choices=["report", "deck", "dashboard"], default="dashboard", help="Optional starting form; author custom HTML when none fits")
args = p.parse_args()
args.destination.mkdir(parents=True, exist_ok=False)
template = (Path(__file__).resolve().parent.parent / f"assets/{args.type}.html").read_text()
(args.destination / "index.html").write_text(template.replace("{{TITLE}}", html.escape(args.title)), encoding="utf-8")
print(args.destination.resolve() / "index.html")
