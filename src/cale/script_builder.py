"""Phase 4a — assemble grouped law segments into one episode script."""

import logging
import re

log = logging.getLogger("cale.script")


def persona_to_text(profile):
    lines = [
        f"{profile.get('name', '')} — {profile.get('role', '')}".strip(" —"),
        f"Country / system: {profile.get('country', '')}".strip(" /:"),
        f"Domain: {profile.get('domain', '')}",
        (profile.get("institution_context") or "").strip(),
        (profile.get("context") or "").strip(),
    ]
    if profile.get("goals"):
        lines.append("Goals: " + "; ".join(profile["goals"]))
    if profile.get("challenges"):
        lines.append("Current challenges: " + "; ".join(profile["challenges"]))
    if profile.get("key_dynamics"):
        lines.append("Power dynamics: " + "; ".join(profile["key_dynamics"]))
    if profile.get("tone_preference"):
        lines.append("Preferred tone: " + profile["tone_preference"])
    return "\n".join(line for line in lines if line and line not in ("Country / system", "Domain:"))


def clean_for_audio(text):
    text = re.sub(r"[*#_`>|]+", "", text)     # strip markdown artifacts
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pause(pauses, key, default):
    """A visible pause marker the renderer turns into silence (or '' if disabled)."""
    if not pauses or not pauses.get("enabled", True):
        return ""
    return f"\n[[pause:{pauses.get(key, default)}]]\n"


def build_episode_script(profile, source, category, segments, pauses=None, with_recap=True):
    """segments: list of {"concept": dict, "application": str}."""
    name = profile.get("name", "there")
    author = source.get("author", "the author")
    title = source.get("title", "the book")
    unit = source.get("unit_label", "concept")
    units = source.get("unit_label_plural", unit + "s")
    names = "; ".join(s["concept"].get("title", "") for s in segments)

    intro = (
        f"Welcome back to your briefing, {name}. "
        f"Today we work through {category} from {author}'s {title}: {names}. "
        f"For each one we'll get the {unit} exactly as {author} described it, then put it "
        f"to work in your world. Let's begin."
    )

    body = []
    for i, s in enumerate(segments):
        c = s["concept"]
        if i:
            body.append(_pause(pauses, "between_concepts", 1.1))
        body.append(f"Number {ordinal_word(i + 1)}. {c.get('title', '')}.")
        body.append(c.get("explanation", "").strip())
        body.append(_pause(pauses, "before_application", 0.6))
        body.append("Now, how this lands for you.")
        body.append(s["application"].strip())

    outro = (
        f"{_pause(pauses, 'before_outro', 1.2)}"
        "That is your briefing. Don't just file these away as ideas. "
        f"Watch for one of these {units} today, and name it the moment you see it. "
        "See you next time."
    )

    recap = ("\n" + _recap(segments) + "\n") if with_recap else "\n"
    full = intro + _pause(pauses, "after_intro", 1.4) + "\n".join(p for p in body if p) + recap + outro
    return clean_for_audio(full)


def polish_script(llm, cfg, script):
    """Optional final pass: smooth into one spoken-word voice via the
    script-assembly skill. Style only — the skill forbids changing substance."""
    from .skills import load_skill

    skill = load_skill("script-assembly")
    low, high = cfg["episode"]["target_words"]
    user = skill.render_input(script=script, low=low, high=high)
    out = llm.chat(skill.system_with("examples.md"), user)
    return clean_for_audio(out)


def build_custom_script(profile, need, segments, pauses=None, with_recap=True):
    """A briefing assembled for a specific situation (Phase 3), not a book category."""
    name = profile.get("name", "there")
    titles = "; ".join(s["concept"].get("title", "") for s in segments)
    intro = (
        f"Welcome, {name}. Here's what you're dealing with: {need.strip()} "
        f"Today we'll work through {len(segments)} ideas that speak directly to it — {titles}. "
        f"For each, the idea itself, then exactly how to use it in your situation. Let's begin.\n\n"
    )
    body = []
    for i, s in enumerate(segments):
        c = s["concept"]
        if i:
            body.append(_pause(pauses, "between_concepts", 1.1))
        body.append(f"Number {ordinal_word(i + 1)}. {c.get('title', '')}.")
        body.append(c.get("explanation", "").strip())
        body.append(_pause(pauses, "before_application", 0.6))
        body.append("Here is how this applies to your situation.")
        body.append(s["application"].strip())
    outro = (f"{_pause(pauses, 'before_outro', 1.2)}"
             "That is your briefing. Pick the one that fit your situation best, and use it this week.")
    recap = ("\n" + _recap(segments) + "\n") if with_recap else "\n"
    return clean_for_audio(intro + _pause(pauses, "after_intro", 1.4)
                           + "\n".join(p for p in body if p) + recap + outro)


_ORDINALS = (r"One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|"
             r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth")
_ORDINAL_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                  "nine", "ten", "eleven", "twelve"]


def ordinal_word(n):
    return _ORDINAL_WORDS[n] if 0 <= n < len(_ORDINAL_WORDS) else str(n)


def _essence(concept, words=22):
    """One memorable line for the recap — the concept's mechanism, trimmed."""
    m = (concept.get("mechanism") or concept.get("explanation") or "").strip()
    m = re.split(r"(?<=[.!?])\s", m)[0].rstrip(".")
    parts = m.split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def _recap(segments):
    """A short numbered recap so the ideas stick — re-walks each concept in a line."""
    lines = ["[[pause:1.3]]", "Before you go, let's lock these in."]
    for i, s in enumerate(segments):
        c = s["concept"]
        lines.append(f"Number {ordinal_word(i + 1)}, {c.get('title', '')}. {_essence(c)}.")
    return "\n".join(lines)


def breathe(text, name=""):
    """Inject REAL pause markers (the renderer turns these into silence; Kokoro's own
    punctuation is too faint). Every serial number gets a beat BEFORE and AFTER it so it
    stands alone; the name and rhetorical questions get one too."""
    # body announcement: "Number one." -> beat before + after, number isolated
    text = re.sub(r"\b(Number)\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b[.,:]?\s+",
                  r" [[pause:0.7]] \1 \2. [[pause:0.6]] ", text, flags=re.I)
    # roadmap serial: "One, Title" -> beat BEFORE the number and AFTER it
    text = re.sub(rf"(?<![A-Za-z])({_ORDINALS})\b\s*[,.…\-–—:]+\s+(?=[\"“A-Z])",
                  r" [[pause:0.5]] \1 [[pause:0.5]] ", text)
    if name:
        text = re.sub(rf"([\w'’])\s*[,.…]?\s+({re.escape(name)})\b",
                      r"\1, [[pause:0.4]] \2", text)
    text = re.sub(r"\?\s+(?=[\"“A-Z])", "? [[pause:0.5]] ", text)
    text = re.sub(r"(\[\[pause:[0-9.]+\]\]\s*){2,}", "[[pause:0.6]] ", text)  # collapse doubles
    return text


def word_count(text):
    return len(text.split())
