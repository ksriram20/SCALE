"""Load skill documents — the externalised intelligence of the pipeline.

A skill lives in `skills/<name>/`:
  - SKILL.md     frontmatter (name, description) + body  -> the SYSTEM prompt
  - input.md     user-message template with {placeholders} -> the per-call input
  - *.md         optional companion files (examples.md, rubric.md) appended on demand

This keeps prompt craft in versioned markdown, not in Python string literals.
Edit a skill to tune the product; the harness code never changes.

Note on braces: only `input.md` is run through str.format, so it must contain
only intended {placeholders}. Keep JSON schemas and literal braces in SKILL.md or
companion files, which are used verbatim.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import ROOT

log = logging.getLogger("cale.skills")

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


@dataclass
class Skill:
    name: str
    description: str
    system: str
    input_template: str
    dir: Path

    def render_input(self, **kwargs):
        return self.input_template.format(**kwargs)

    def resource(self, filename):
        path = self.dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def system_with(self, *filenames):
        """System prompt plus appended companion files (examples, rubric, ...)."""
        parts = [self.system]
        for fn in filenames:
            content = self.resource(fn)
            if content:
                parts.append(f"\n\n---\n# Reference: {fn}\n\n{content}")
        return "".join(parts)


def _parse_frontmatter(text):
    if text.lstrip().startswith("---"):
        _, fm, body = text.split("---", 2)
        return (yaml.safe_load(fm) or {}), body.strip()
    return {}, text.strip()


def load_skill(name, skills_dir=None):
    base = Path(skills_dir) if skills_dir else ROOT / "skills"
    sdir = base / name
    skill_md = sdir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"skill not found: {skill_md}")
    meta, body = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    input_md = sdir / "input.md"
    input_template = input_md.read_text(encoding="utf-8") if input_md.exists() else "{input}"
    log.info("loaded skill: %s", name)
    return Skill(
        name=meta.get("name", name),
        description=meta.get("description", ""),
        system=body,
        input_template=input_template,
        dir=sdir,
    )


def iter_skill_names(skills_dir=None):
    base = Path(skills_dir) if skills_dir else ROOT / "skills"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if (p / "SKILL.md").exists())


def lint_skill(name, skills_dir=None):
    """Return (info_dict, warnings_list) for one skill.

    Catches the failure modes that would break the harness at runtime: missing
    frontmatter, a thin body, and stray `{`/`}` in input.md that would crash
    str.format (the inserted runtime values may contain braces freely; the
    template itself may not, except doubled {{ }}).
    """
    warnings = []
    base = Path(skills_dir) if skills_dir else ROOT / "skills"
    sdir = base / name
    meta, body = _parse_frontmatter((sdir / "SKILL.md").read_text(encoding="utf-8"))

    if not meta.get("name"):
        warnings.append("SKILL.md frontmatter missing 'name'")
    if not meta.get("description"):
        warnings.append("SKILL.md frontmatter missing 'description'")
    if len(body) < 80:
        warnings.append("SKILL.md body looks thin (<80 chars)")

    fields = []
    input_md = sdir / "input.md"
    if input_md.exists():
        text = input_md.read_text(encoding="utf-8")
        fields = sorted(set(PLACEHOLDER_RE.findall(text)))
        stripped = PLACEHOLDER_RE.sub("", text).replace("{{", "").replace("}}", "")
        if "{" in stripped or "}" in stripped:
            warnings.append("input.md has a stray '{' or '}' — will break str.format")
    else:
        warnings.append("no input.md (skill used as reference-only?)")

    companions = sorted(
        p.name for p in sdir.glob("*.md") if p.name not in ("SKILL.md", "input.md")
    )
    info = {
        "name": meta.get("name", name),
        "dir": name,
        "description": meta.get("description", ""),
        "fields": fields,
        "companions": companions,
    }
    return info, warnings
