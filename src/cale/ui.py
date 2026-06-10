"""SCALE UI (Gradio) — 5-tab design.

Dashboard · Brief · Profile · Library · Settings
Launch: scale ui
Bare host: KOKORO_BASE_URL=http://localhost:8880/v1 scale ui
"""

import logging
import os
import shutil
from pathlib import Path

from .config import ROOT, load_config, load_profile, profile_path, validate_profile

log = logging.getLogger("cale.ui")

_STATIC_VOICES = [
    "am_onyx", "am_adam", "am_fenrir", "bm_george", "bm_lewis", "af_bella", "af_sky",
]

_PRESETS = [
    ("Dark Philosopher",  "am_onyx(0.7)+am_adam(0.3)",   "Deep & confident — the default"),
    ("Oxford Villain",    "bm_george(0.6)+am_onyx(0.4)", "British + raspy gravitas"),
    ("Gritty Tactician",  "am_fenrir(0.5)+am_onyx(0.5)", "Rugged, direct"),
    ("Pure Depth",        "am_onyx",                      "Maximum bass, no blend"),
]
_PRESET_NAMES  = [p[0] for p in _PRESETS]
_PRESET_BLENDS = {p[0]: p[1] for p in _PRESETS}


def _kokoro_base(cfg):
    return os.environ.get("KOKORO_BASE_URL") or cfg["tts"]["base_url"]


def get_voices():
    import json
    import urllib.request
    try:
        base = _kokoro_base(load_config()).rstrip("/")
        d = json.load(urllib.request.urlopen(f"{base}/audio/voices", timeout=8))
        return sorted(v["id"] for v in d["voices"])
    except Exception as e:
        log.warning("voice list fetch failed (%s) — using static list", e)
        return _STATIC_VOICES


# ---- chatbot helpers ---------------------------------------------------

def _bot(text):
    return {"role": "assistant", "content": text}


def _user(text):
    return {"role": "user", "content": text}


# ---- dashboard ---------------------------------------------------------

def dashboard_stats():
    try:
        from .pipeline import library_summary
        counts, q = library_summary()
        books    = len(counts)
        concepts = sum(counts.values())
        vectors  = q if q is not None else "unavailable"
        lines = [f"### {books} book{'s' if books != 1 else ''} · {concepts} concepts · {vectors} vectors indexed\n"]
        for b, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"- **{b}** — {c} concepts")
        return "\n".join(lines)
    except Exception as e:
        return f"_(library unavailable: {e})_"


# ---- brief: two-step — scan (no LLM) then generate --------------------

def scan_concepts(need):
    import gradio as gr
    from .embed import embed
    from .vectorstore import search

    if not (need or "").strip():
        return "Enter your situation above first.", gr.update(maximum=20, value=1, interactive=False)
    try:
        hits = search(embed([need])[0], top_k=20)
    except Exception as e:
        return f"Vector DB error — is Qdrant running? ({e})", gr.update(maximum=20, value=1, interactive=False)

    candidates = [payload for _, payload in hits]
    n = len(candidates)
    if not n:
        return "No concepts found — add and ingest books first.", gr.update(maximum=20, value=1, interactive=False)

    lines = [f"**{n} concept(s) match your situation.** Set how many to include, then generate:\n"]
    for c in candidates:
        lines.append(f"- **{c['title']}** _[{c.get('category', '')}]_")
    return "\n".join(lines), gr.update(maximum=n, value=min(4, n), interactive=True)


def generate_brief(need, n_concepts, auto_duration, minutes):
    from .pipeline import build_custom_episode

    if not (need or "").strip():
        return "Enter your situation first.", ""
    mins = 20 if auto_duration else int(minutes)
    path, chosen = build_custom_episode(need, mins, render=False)
    chosen = chosen[:int(n_concepts)]
    lines = [f"**Briefing built from {len(chosen)} concept(s):**\n"]
    for c in chosen:
        lines.append(f"- **{c['title']}** _[{c.get('category')}]_ — {c.get('why', '')}")
    return "\n".join(lines), Path(path).read_text(encoding="utf-8")


def compose_blend(v1, w1, v2, w2, v3, w3):
    """Compose a Kokoro blend string from up to 3 voices with integer weights."""
    parts = [(v, w) for v, w in [(v1, w1), (v2, w2), (v3, w3)] if v and (w or 0) > 0]
    if not parts:
        return ""
    total = sum(w for _, w in parts)
    return "+".join(f"{v}({round(w / total, 2)})" for v, w in parts)


def render_brief(preset_name, custom_blend, use_custom, speed, master_on):
    from .pipeline import produce_audio, _read_meta

    cfg = load_config()
    script_dir = ROOT / cfg["output"]["script_dir"]
    sp = script_dir / "brief.txt"
    if not sp.exists():
        return None, "Generate a briefing first."
    voice = (custom_blend or "").strip() if use_custom else _PRESET_BLENDS.get(preset_name, _PRESETS[0][1])
    cfg["tts"]["voice"] = voice or _PRESETS[0][1]
    cfg["tts"]["speed"] = float(speed)
    cfg["tts"].setdefault("master", {})["enabled"] = bool(master_on)
    meta = _read_meta(script_dir, "brief", "SCALE Brief")
    out  = produce_audio(cfg, sp.read_text(encoding="utf-8"), meta)
    return str(out), f"Rendered → {out}"


# ---- profile -----------------------------------------------------------

def profile_text():
    p = profile_path()
    return p.read_text(encoding="utf-8") if p.exists() else ""


def profile_save(text):
    profile_path().write_text(text, encoding="utf-8")
    return "Saved ✓"


def profile_validate():
    problems = validate_profile(load_profile())
    return "Profile OK ✓" if not problems else "Issues:\n- " + "\n- ".join(problems)


def ctx_start():
    from .context_engine import interview_step, save_profile
    profile = {}
    kind, text = interview_step([], profile)
    state = {"transcript": [], "last_q": text, "profile": profile, "done": False}
    if kind == "profile":
        save_profile(text)
        return [_bot("Profile already complete.")], {**state, "done": True}
    return [_bot(text)], state


def ctx_respond(message, history, state):
    from .context_engine import interview_step, save_profile
    history = (history or []) + [_user(message)]
    if state.get("done"):
        return history + [_bot("Interview finished. Hit Start / Restart to redo.")], state
    tr = state["transcript"] + [f"Interviewer: {state['last_q']}", f"User: {message}"]
    kind, payload = interview_step(tr, state["profile"])
    if kind == "profile":
        save_profile(payload)
        import yaml
        msg = "Profile saved:\n\n```yaml\n" + yaml.safe_dump(
            payload, sort_keys=False, allow_unicode=True) + "```"
        return history + [_bot(msg)], {**state, "transcript": tr, "done": True}
    return history + [_bot(payload)], {**state, "transcript": tr, "last_q": payload}


# ---- library -----------------------------------------------------------

def pending_view():
    from .pipeline import pending_books
    p = pending_books()
    if not p:
        return "(none — every book in data/books/ is ingested)"
    return "Not yet ingested:\n" + "\n".join(f"  • {x}" for x in p)


def upload_book(file):
    if not file:
        return "No file selected."
    bd = ROOT / load_config()["ingest"]["book_dir"]
    bd.mkdir(parents=True, exist_ok=True)
    dest = bd / Path(file.name).name
    shutil.copy(file.name, dest)
    os.chmod(dest, 0o644)
    return f"Added {dest.name} — click Sync to ingest."


# ---- settings ----------------------------------------------------------

def settings_text():
    cfg    = load_config()
    llm    = cfg["llm"]
    key_env = llm.get("api_key_env", "OPENROUTER_API_KEY")
    key    = "set ✓" if os.environ.get(key_env) else f"MISSING — add {key_env} to .env"
    models = "\n  ".join(llm["models"])
    return (f"Provider : {llm.get('provider')}  {llm.get('base_url')}\n"
            f"{key_env}: {key}\nFree-only: {llm.get('free_only')}\n"
            f"Kokoro   : {_kokoro_base(cfg)}\nModels:\n  {models}")


def test_llm():
    try:
        from .llm import OpenRouterClient
        resp = OpenRouterClient(load_config()).chat("You are a test.", "Reply with exactly: OK", temperature=0)
        return f"LLM OK ✓  ({resp[:80]})"
    except Exception as e:
        return f"LLM FAILED: {e}"


def test_tts():
    try:
        import urllib.request
        urllib.request.urlopen(_kokoro_base(load_config()).rstrip("/") + "/audio/voices", timeout=5)
        return "Kokoro TTS OK ✓"
    except Exception as e:
        return f"Kokoro FAILED: {e}"


# ---- app ---------------------------------------------------------------

def launch_ui(share=False):
    import gradio as gr

    voices = get_voices()
    v1_default = voices[0] if voices else None
    v2_default = voices[1] if len(voices) > 1 else None

    with gr.Blocks(title="SCALE", theme=gr.themes.Soft()) as app:
        gr.Markdown("# SCALE — Synthesized Contextual Audio Learning Engine")

        # ── 1. Dashboard ────────────────────────────────────────────────
        with gr.Tab("Dashboard"):
            dash_stats   = gr.Markdown(dashboard_stats())
            dash_refresh = gr.Button("Refresh", size="sm")
            gr.Markdown(
                "\n---\n**Getting started:** go to **Brief**, describe your situation, "
                "and SCALE finds the best-fitting concepts from the library and writes "
                "a bespoke audio briefing tailored to you."
            )
            dash_refresh.click(dashboard_stats, outputs=dash_stats)

        # ── 2. Brief ────────────────────────────────────────────────────
        with gr.Tab("Brief"):
            gr.Markdown(
                "Describe what you're dealing with. SCALE scans the library instantly, "
                "lets you choose how many concepts to pack in, then writes and voices your briefing."
            )

            need     = gr.Textbox(label="Your situation", lines=3,
                                  placeholder="e.g. I need to deliver a session to faculty on practical AI skills…")
            scan_btn = gr.Button("Scan library", variant="secondary")

            concept_list = gr.Markdown("_(click Scan to see what's available for your situation)_")
            n_concepts   = gr.Slider(1, 20, value=1, step=1,
                                     label="Number of concepts to include", interactive=False)

            with gr.Row():
                auto_dur = gr.Checkbox(value=False, label="Let SCALE decide duration")
                minutes  = gr.Slider(5, 60, value=20, step=5, label="Max duration (minutes)")

            gen_btn      = gr.Button("Write my briefing", variant="primary")
            matched_md   = gr.Markdown()
            brief_script = gr.Textbox(label="Your briefing", lines=16)

            scan_btn.click(scan_concepts, [need], [concept_list, n_concepts])
            auto_dur.change(lambda x: gr.update(visible=not x), auto_dur, minutes)
            gen_btn.click(generate_brief, [need, n_concepts, auto_dur, minutes],
                          [matched_md, brief_script])

            gr.Markdown("### Voice & audio")
            preset = gr.Radio(_PRESET_NAMES, value=_PRESET_NAMES[0], label="Voice preset")
            for name, blend, desc in _PRESETS:
                gr.Markdown(f"_{name}_: `{blend}` — {desc}", visible=False)  # hidden reference

            with gr.Accordion("Custom voice blend", open=False):
                gr.Markdown(
                    "Mix up to 3 voices by weight (integers — they're normalized automatically). "
                    "[Browse all Kokoro voices ↗](https://huggingface.co/hexgrad/Kokoro-82M)"
                )
                with gr.Row():
                    mix_v1 = gr.Dropdown(voices, value=v1_default, label="Voice 1")
                    mix_w1 = gr.Slider(0, 10, value=7, step=1, label="Weight")
                with gr.Row():
                    mix_v2 = gr.Dropdown(voices, value=v2_default, label="Voice 2")
                    mix_w2 = gr.Slider(0, 10, value=3, step=1, label="Weight")
                with gr.Row():
                    mix_v3 = gr.Dropdown(voices, value=None, label="Voice 3 (optional)")
                    mix_w3 = gr.Slider(0, 10, value=0, step=1, label="Weight")

                blend_preview = gr.Textbox(label="Blend string", interactive=False,
                                           info="Paste this into config.yaml or use via the checkbox below")
                use_custom    = gr.Checkbox(value=False, label="Use this custom blend for rendering")

                for ctrl in [mix_v1, mix_w1, mix_v2, mix_w2, mix_v3, mix_w3]:
                    ctrl.change(compose_blend,
                                [mix_v1, mix_w1, mix_v2, mix_w2, mix_v3, mix_w3],
                                blend_preview)

            with gr.Row():
                speed  = gr.Slider(0.7, 1.1, value=0.85, step=0.01, label="Speed")
                master = gr.Checkbox(value=True, label="Master (deep / bassy)")

            render_btn    = gr.Button("Render audio", variant="primary")
            audio_out     = gr.Audio(label="Briefing audio", type="filepath")
            render_status = gr.Markdown()
            render_btn.click(render_brief,
                             [preset, blend_preview, use_custom, speed, master],
                             [audio_out, render_status])

        # ── 3. Profile ──────────────────────────────────────────────────
        with gr.Tab("Profile"):
            gr.Markdown(
                "Your profile tells SCALE who you are and what style of insight you need. "
                "Edit the YAML directly, or let the interview build it for you."
            )
            ptext = gr.Code(value=profile_text(), language="yaml", label="config/profile.yaml")
            with gr.Row():
                pload = gr.Button("Reload")
                psave = gr.Button("Save", variant="primary")
                pval  = gr.Button("Validate")
            pstatus = gr.Markdown()
            pload.click(profile_text, outputs=ptext)
            psave.click(profile_save, ptext, pstatus)
            pval.click(profile_validate, outputs=pstatus)

            with gr.Accordion("Build profile via interview (optional)", open=False):
                gr.Markdown(
                    "A gentle conversation that writes the YAML for you. "
                    "Share as much or as little as you like."
                )
                chat   = gr.Chatbot(height=340)
                cstate = gr.State({})
                cmsg   = gr.Textbox(placeholder="Your answer…", label="")
                cstart = gr.Button("Start / Restart interview")
                cstart.click(ctx_start, outputs=[chat, cstate])
                cmsg.submit(ctx_respond, [cmsg, chat, cstate], [chat, cstate]).then(
                    lambda: "", None, cmsg)

        # ── 4. Library ──────────────────────────────────────────────────
        with gr.Tab("Library"):
            libview    = gr.Markdown(dashboard_stats())
            librefresh = gr.Button("Refresh", size="sm")

            gr.Markdown("### Pending ingestion")
            pendview = gr.Code(value=pending_view(), label="Books not yet ingested")
            syncbtn  = gr.Button("⟳ Sync — ingest pending books", variant="primary")
            syncstatus = gr.Markdown()

            def _sync(progress=gr.Progress()):
                from .pipeline import sync_books
                progress(0.0, desc="scanning…")
                def cb(done, total, title, book):
                    progress(done / max(total, 1),
                             desc=f"{book[:18]} · {title[:30]} ({done}/{total})")
                _, results = sync_books(on_progress=cb)
                msg = ("**Synced:**\n" + "\n".join(f"- {r}" for r in results)) if results \
                    else "Nothing pending — all books already ingested."
                return dashboard_stats(), pending_view(), msg

            librefresh.click(lambda: (dashboard_stats(), pending_view()),
                             outputs=[libview, pendview])
            syncbtn.click(_sync, outputs=[libview, pendview, syncstatus])

            gr.Markdown("### Upload a new book")
            up       = gr.File(label="PDF / EPUB / TXT — then click Sync to ingest")
            upstatus = gr.Markdown()
            up.upload(upload_book, up, upstatus).then(pending_view, None, pendview)

        # ── 5. Settings ─────────────────────────────────────────────────
        with gr.Tab("Settings"):
            gr.Markdown("### LLM provider")
            gr.Markdown(
                "To switch providers (NIM → OpenRouter → Ollama), edit `config/config.yaml` "
                "and restart the container. API keys go in `.env`."
            )
            llm_status = gr.Code(value=settings_text(), label="Active configuration")
            with gr.Row():
                llm_reload    = gr.Button("Reload config", size="sm")
                test_llm_btn  = gr.Button("Test LLM connection")
                test_tts_btn  = gr.Button("Test Kokoro TTS")
            conn_status = gr.Markdown()
            llm_reload.click(settings_text, outputs=llm_status)
            test_llm_btn.click(test_llm, outputs=conn_status)
            test_tts_btn.click(test_tts, outputs=conn_status)

    app.launch(server_name="0.0.0.0", server_port=7860, share=share)
