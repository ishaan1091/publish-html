#!/usr/bin/env python3
"""Install thin harness pointers to this clone. No publishing or copied logic."""
import argparse
from pathlib import Path
import sys

START = "<!-- publish-html:start -->"
END = "<!-- publish-html:end -->"


def install(harness, home, skill_dir=None, uninstall=False):
    source = Path(__file__).resolve().parent.parent
    harnesses = ["claude", "codex"] if harness == "both" else [harness] if harness else []
    links = [Path(skill_dir).expanduser().absolute()] if skill_dir else [home / ("." + h) / "skills/publish-html" for h in harnesses]
    # Preflight all targets before writing any of them.
    for link in links:
        if (link.exists() or link.is_symlink()) and link.resolve() != source:
            raise ValueError(f"Existing installation at {link}; move it yourself before installing. Nothing replaced.")
    agents = home / ".codex/AGENTS.md"
    original = agents.read_text() if agents.exists() else ""
    updated = original
    if uninstall:
        for link in links:
            if link.is_symlink() and link.resolve() == source:
                link.unlink()
                print(f"Removed pointer {link}")
        if "codex" in harnesses and START in original and END in original:
            start, rest = original.split(START, 1)
            block, end = rest.split(END, 1)
            if str(source) in block:
                agents.write_text(start + end)
        return
    if "codex" in harnesses:
        if START in original or END in original:
            if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
                raise ValueError("Malformed publish-html block in AGENTS.md. Repair it before installing.")
        block = f"""{START}
For requests to turn supplied analysis/text/data into a report, deck, dashboard, visualization, or published HTML, read [{source.name}]({source / 'SKILL.md'}).
Invoking this skill for a deliverable includes publishing through `{source / 'publish.sh'}` and returning a verified public URL. Reuse its registered repository; set up Pages if missing. Do not perform the underlying research. Comments are optional and never required for publication. Keep a draft local only when explicitly instructed. Never publish secrets or work/employer-confidential data.
{END}"""
        if START in original:
            start, rest = original.split(START, 1)
            _, end = rest.split(END, 1)
            updated = start + block + end
        else:
            updated = original + ("\n\n" if original else "") + block + "\n"
    for link in links:
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.exists() and not link.is_symlink():
            link.symlink_to(source, target_is_directory=True)
        print(f"{link} -> {source}")
    if "codex" in harnesses:
        if original != updated:
            if agents.exists():
                backup = agents.with_name("AGENTS.md.before-publish-html")
                if not backup.exists():
                    backup.write_text(original)
            agents.parent.mkdir(parents=True, exist_ok=True)
            agents.write_text(updated)
        print(agents)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--harness", choices=["claude", "codex", "both"])
    group.add_argument("--skill-dir", type=Path, help="Exact destination for any harness; installs a symlink to this clone")
    p.add_argument("--uninstall", action="store_true", help="Remove only owned symlinks and the managed Codex pointer; retain backups")
    args = p.parse_args()
    try:
        install(args.harness, Path.home(), args.skill_dir, args.uninstall)
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
