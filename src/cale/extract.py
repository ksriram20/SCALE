"""Phase 1 — extract a unit as a grounded concept (faithful + cited).

The cognitive instructions live in skills/concept-extraction/. This module is
thin glue: load the skill, render the input with the book + unit identity, call
the model, cache by slug.
"""

import json
import logging

from .config import ROOT
from .ingest import slugify
from .skills import load_skill

log = logging.getLogger("cale.extract")


def extract_concept(llm, cfg, source, unit):
    book_id = slugify(source.get("title", "book"))
    cache = ROOT / cfg["ingest"]["cache_dir"] / book_id / f"{unit['slug']}.json"
    if cache.exists():
        log.info("cache hit: %s", unit["title"])
        data = json.loads(cache.read_text())
    else:
        skill = load_skill("concept-extraction")
        system = skill.system_with("examples.md")
        user = skill.render_input(
            book_title=source["title"],
            book_author=source["author"],
            unit_label=source["unit_label"],
            unit_label_upper=source["unit_label"].upper(),
            unit_title=unit["title"],
            category=unit["category"],
            source=unit["text"][:14000],
            concept_words=cfg["episode"]["concept_words"],
        )
        raw = llm.chat(system, user, json_mode=True)
        data = parse_json(raw)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        log.info("extracted: %s", data.get("title"))

    # Canonical metadata from source.yaml always wins (clean, consistent titles).
    data["title"] = unit["title"]
    data["slug"] = unit["slug"]
    data["category"] = unit["category"]
    return data


def parse_json(raw):
    """Tolerant JSON parse — strips ```json fences some models emit."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lstrip().lower().startswith("json"):
            raw = raw.lstrip()[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    # strict=False tolerates raw newlines/tabs inside strings (common from free models).
    return json.loads(raw, strict=False)
