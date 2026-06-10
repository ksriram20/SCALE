"""Phase 3 — the matcher: a person's situation -> the best-fitting concepts.

Retrieve broadly with the vector DB, then let the LLM re-rank for TRUE fit,
diversify, and pack to a time budget. Vector search gives candidates; the model's
judgement gives quality.
"""

import logging

from .config import load_config, load_profile
from .extract import parse_json
from .llm import OpenRouterClient
from .script_builder import persona_to_text
from .skills import load_skill

log = logging.getLogger("cale.matcher")


def match(need, profile=None, target_k=4, pool=None):
    """Return up to `target_k` ordered concept records (Qdrant payloads), each
    annotated with a 'why' rationale. Retrieve a wider pool, then LLM re-ranks."""
    from .embed import embed
    from .vectorstore import search

    cfg = load_config()
    profile = profile if profile is not None else load_profile()
    target_k = max(1, int(target_k))
    pool = pool or max(12, target_k * 3)

    hits = search(embed([need])[0], top_k=pool)
    candidates = [payload for _, payload in hits]
    if not candidates:
        return []
    by_slug = {c["slug"]: c for c in candidates}

    skill = load_skill("concept-matching")
    cand_lines = "\n".join(
        f"- slug: {c['slug']} | {c['title']} [{c.get('category','')}] — {c.get('mechanism', '')[:170]}"
        for c in candidates
    )
    llm = OpenRouterClient(cfg)
    raw = llm.chat(
        skill.system,
        skill.render_input(
            need=need,
            persona=persona_to_text(profile),
            target_k=target_k,
            candidates=cand_lines,
        ),
        json_mode=True,
    )
    try:
        selected = parse_json(raw).get("selected", [])
    except Exception:
        log.warning("matcher: could not parse selection — falling back to top-%d by vector", target_k)
        selected = [{"slug": c["slug"], "why": ""} for c in candidates[:target_k]]

    chosen = []
    for s in selected:
        rec = by_slug.get(s.get("slug"))
        if rec and rec["slug"] not in {c["slug"] for c in chosen}:
            rec = dict(rec)
            rec["why"] = s.get("why", "")
            chosen.append(rec)
    log.info("matched %d concepts for need (target %d): %s",
             len(chosen), target_k, [c["title"] for c in chosen])
    return chosen[:target_k]
