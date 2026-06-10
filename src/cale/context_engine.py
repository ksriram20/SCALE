"""Conversational context engine — an LLM interview that builds/enriches the profile.

Runs a short back-and-forth: the context-interview skill asks one question at a
time, adapting to answers, then emits a structured profile that replaces
config/profile.yaml (the previous file is backed up). The future UI reuses this
same logic; the CLI just wires stdin/stdout to it.
"""

import logging
import re

import yaml

from .config import load_config, load_profile, profile_path
from .extract import parse_json
from .llm import OpenRouterClient
from .skills import load_skill

log = logging.getLogger("cale.context")

_PROFILE_BLOCK = re.compile(r"```profile\s*(\{.*?\})\s*```", re.S)
_QUESTION = re.compile(r"QUESTION:\s*(.+)", re.S)


def _profile_yaml(profile):
    return yaml.safe_dump(profile, sort_keys=False, allow_unicode=True)


def _extract_profile(text):
    m = _PROFILE_BLOCK.search(text)
    if not m:
        return None
    try:
        return parse_json(m.group(1))
    except Exception:
        return None


def _extract_question(text):
    m = _QUESTION.search(text)
    return (m.group(1) if m else text).strip()


def save_profile(profile):
    path = profile_path()
    if path.exists():
        backup = path.parent / (path.name + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(_profile_yaml(profile), encoding="utf-8")


# back-compat alias
_save = save_profile


def interview_step(transcript, current_profile):
    """One interview turn. Returns ('question', text) or ('profile', dict).

    Stateless: caller holds the transcript (list of 'Interviewer: ...' / 'User: ...'
    lines) and the current profile dict. Used by both the CLI loop and the UI chat.
    """
    cfg = load_config()
    llm = OpenRouterClient(cfg)
    skill = load_skill("context-interview")
    reply = llm.chat(
        skill.system,
        skill.render_input(
            current_profile=_profile_yaml(current_profile) if current_profile else "(none yet)",
            transcript="\n".join(transcript) if transcript else "(empty)",
        ),
    )
    profile = _extract_profile(reply)
    if profile is not None:
        return ("profile", profile)
    return ("question", _extract_question(reply))


def run_interview(input_fn=input, output_fn=print, max_turns=12):
    cfg = load_config()
    llm = OpenRouterClient(cfg)
    skill = load_skill("context-interview")

    try:
        current = load_profile() or {}
    except Exception:
        current = {}

    transcript = []
    output_fn(
        "\n[context] I'll ask a few short questions to understand your real world "
        "(country, institution, the power dynamics you face) so the advice fits.\n"
        "Answer each, press Enter. Type 'done' anytime to finish.\n"
    )

    for _ in range(max_turns):
        reply = llm.chat(
            skill.system,
            skill.render_input(
                current_profile=_profile_yaml(current) if current else "(none yet)",
                transcript="\n".join(transcript) if transcript else "(empty)",
            ),
        )

        profile = _extract_profile(reply)
        if profile is not None:
            _save(profile)
            output_fn(f"\n[context] Enriched profile saved to {profile_path()}")
            output_fn("[context] Backup of the previous profile: profile.yaml.bak\n")
            return profile

        question = _extract_question(reply)
        output_fn("\n" + question)
        answer = input_fn("> ").strip()
        transcript.append("Interviewer: " + question)

        if answer.lower() in ("done", "stop", "quit", "exit", ""):
            transcript.append("User: (asks to finish — produce the final profile now)")
            reply = llm.chat(
                skill.system,
                skill.render_input(
                    current_profile=_profile_yaml(current) if current else "(none)",
                    transcript="\n".join(transcript),
                ),
            )
            profile = _extract_profile(reply)
            if profile is not None:
                _save(profile)
                output_fn(f"\n[context] Saved enriched profile to {profile_path()}\n")
                return profile
            output_fn("[context] Couldn't finalize a profile — nothing saved.")
            return None

        transcript.append("User: " + answer)

    output_fn("[context] Reached the question limit without a final profile — nothing saved.")
    return None
