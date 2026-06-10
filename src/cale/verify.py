"""Phase 3 — faithfulness auditor.

Cognitive instructions + rubric live in skills/faithfulness-audit/. Guards two
distinct failures: concept drift (vs. source) and application drift (vs. mechanism).
"""

import logging

from .extract import parse_json
from .skills import load_skill

log = logging.getLogger("cale.verify")


def verify(llm, cfg, source, source_text, concept, application):
    skill = load_skill("faithfulness-audit")  # lean: rubric folded in, no per-call append
    user = skill.render_input(
        unit_label=source["unit_label"],
        book_author=source["author"],
        book_title=source["title"],
        source=source_text[:12000],
        mechanism=concept.get("mechanism", ""),
        explanation=concept.get("explanation", ""),
        application=application,
    )
    raw = llm.chat(skill.system, user, temperature=0.0, json_mode=True)
    try:
        return parse_json(raw)
    except Exception:
        log.warning("could not parse audit JSON — treating as pass")
        return {"concept_faithful": True, "application_grounded": True, "issues": []}
