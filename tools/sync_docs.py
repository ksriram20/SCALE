#!/usr/bin/env python3
"""Auto-sync the *reference* sections of README.md and ARCHITECTURE.md.

Regenerates the factual parts that drift — CLI commands, skills, source modules —
straight from the repo, and injects them between marker comments:

    <!-- AUTO:commands -->  ... generated ...  <!-- /AUTO:commands -->
    <!-- AUTO:skills -->    ...               <!-- /AUTO:skills -->
    <!-- AUTO:modules -->   ...               <!-- /AUTO:modules -->

Hand-written prose is never touched. Run by the Stop hook after each change, or
manually: `python3 tools/sync_docs.py`.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gen_commands():
    txt = (ROOT / "src/cale/cli.py").read_text()
    seen, rows = set(), []
    for name, help_ in re.findall(r'add_parser\(\s*"([^"]+)"\s*,\s*help\s*=\s*"([^"]+)"', txt):
        if name in seen:
            continue
        seen.add(name)
        rows.append(f"| `scale {name}` | {help_} |")
    return "| Command | What |\n|---|---|\n" + "\n".join(rows)


def _frontmatter(md):
    out = {}
    if md.lstrip().startswith("---"):
        for line in md.split("---", 2)[1].splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def gen_skills():
    rows = []
    for d in sorted((ROOT / "skills").iterdir()):
        sk = d / "SKILL.md"
        if not sk.exists():
            continue
        fm = _frontmatter(sk.read_text())
        desc = fm.get("description", "")
        desc = desc.split(". ")[0]              # first sentence only
        if len(desc) > 120:
            desc = desc[:117].rstrip() + "…"
        rows.append(f"- **{fm.get('name', d.name)}** — {desc}")
    return "\n".join(rows)


def gen_modules():
    rows = []
    for p in sorted((ROOT / "src/cale").glob("*.py")):
        if p.name == "__init__.py":
            continue
        m = re.search(r'(?:"""|\'\'\')[ \t]*\n?[ \t]*(.+)', p.read_text())
        first = (m.group(1).strip().rstrip('"').strip() if m else "")
        rows.append(f"- `{p.name}` — {first}")
    return "\n".join(rows)


GENERATORS = {"commands": gen_commands, "skills": gen_skills, "modules": gen_modules}


def sync(path):
    if not path.exists():
        return False
    text = original = path.read_text()
    for name, gen in GENERATORS.items():
        pat = re.compile(rf"<!-- AUTO:{name} -->.*?<!-- /AUTO:{name} -->", re.S)
        if pat.search(text):
            block = f"<!-- AUTO:{name} -->\n{gen()}\n<!-- /AUTO:{name} -->"
            text = pat.sub(lambda m, b=block: b, text)
    if text != original:
        path.write_text(text)
        return True
    return False


if __name__ == "__main__":
    for f in ("README.md", "ARCHITECTURE.md"):
        if sync(ROOT / f):
            print(f"synced {f}")
