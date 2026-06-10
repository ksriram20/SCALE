"""Phase 2 — synthesize the persona-specific application of a concept.

Cognitive instructions live in skills/application-synthesis/ (with the
persona-modeling skill appended). Thin glue: wire book + concept + persona into
the skill and call the model.
"""

import logging

from .skills import load_skill

log = logging.getLogger("cale.synthesize")


def synthesize_application(llm, cfg, source, concept, persona_text, domain, locale=""):
    # Lean, self-sufficient skill (locale + anchor + a tiny example are inline) — no
    # heavy per-call appends, so each of these (per concept, x regenerations) is cheaper.
    skill = load_skill("application-synthesis")
    user = skill.render_input(
        unit_label=source["unit_label"],
        book_author=source["author"],
        book_title=source["title"],
        title=concept.get("title", ""),
        mechanism=concept.get("mechanism", ""),
        explanation=concept.get("explanation", ""),
        persona=persona_text,
        domain=domain,
        locale=locale or "(use the country stated in the profile)",
        stance=source.get("application_stance", "both"),
        application_words=cfg["episode"]["application_words"],
    )
    return llm.chat(skill.system, user)
