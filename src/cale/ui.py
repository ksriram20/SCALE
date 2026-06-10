"""Temporary SCALE UI (Gradio).

Wraps the existing engine — context interview, profile editing, episode generation,
and voice/mastering + playback. Launch with `scale ui`.

On a bare host, point it at the local Kokoro container:
    KOKORO_BASE_URL=http://localhost:8880/v1 scale ui
(Inside docker-compose the default `kokoro:8880` already resolves.)
"""

import logging
import os
import shutil
from pathlib import Path

from .config import ROOT, load_config, load_profile, profile_path, validate_profile

log = logging.getLogger("cale.ui")

_STATIC_VOICES = [
    "am_onyx(0.7)+am_adam(0.3)", "bm_george(0.6)+am_onyx(0.4)",
    "am_fenrir(0.5)+am_onyx(0.5)", "am_onyx", "am_adam", "am_fenrir",
    "bm_george", "bm_lewis", "af_bella", "af_sky",
]


def _kokoro_base(cfg):
    return os.environ.get("KOKORO_BASE_URL") or cfg["tts"]["base_url"]


def get_voices():
    import json
    import urllib.request

    try:
        base = _kokoro_base(load_config()).rstrip("/")
        d = json.load(urllib.request.urlopen(f"{base}/audio/voices", timeout=8))
        ids = [v["id"] for v in d["voices"]]
        # surface the curated blends first, then all single voices
        return _STATIC_VOICES[:3] + sorted(ids)
    except Exception as e:
        log.warning("voice list fetch failed (%s) — using static list", e)
        return _STATIC_VOICES


# ---- handlers (no gradio import needed) -----------------------------------

def _bot(text):
    return {"role": "assistant", "content": text}


def _user(text):
    return {"role": "user", "content": text}


def ctx_start():
    from .context_engine import interview_step, save_profile

    # Always start from a blank slate: meet the person fresh, don't assume who they are.
    profile = {}
    kind, text = interview_step([], profile)
    state = {"transcript": [], "last_q": text, "profile": profile, "done": False}
    if kind == "profile":
        save_profile(text)
        return [_bot("Profile already complete and saved.")], {**state, "done": True}
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
        msg = "Saved your enriched profile:\n\n```\n" + yaml.safe_dump(
            payload, sort_keys=False, allow_unicode=True) + "```"
        return history + [_bot(msg)], {**state, "transcript": tr, "done": True}
    return history + [_bot(payload)], {**state, "transcript": tr, "last_q": payload}


def profile_text():
    p = profile_path()
    return p.read_text(encoding="utf-8") if p.exists() else ""


def profile_save(text):
    profile_path().write_text(text, encoding="utf-8")
    return "Saved config/profile.yaml"


def profile_validate():
    problems = validate_profile(load_profile())
    return "Profile OK ✓" if not problems else "Issues:\n- " + "\n- ".join(problems)


def generate_brief(need, minutes):
    from .pipeline import build_custom_episode

    if not (need or "").strip():
        return "Enter your situation first.", ""
    path, chosen = build_custom_episode(need, int(minutes), render=False)
    lines = [f"**Matched {len(chosen)} concept(s) to your situation:**", ""]
    for c in chosen:
        lines.append(f"- **{c['title']}**  _[{c.get('category')}]_ — {c.get('why','')}")
    return "\n".join(lines), Path(path).read_text(encoding="utf-8")


def render_brief(voice, speed, master_on):
    from .pipeline import produce_audio, _read_meta

    cfg = load_config()
    script_dir = ROOT / cfg["output"]["script_dir"]
    sp = script_dir / "brief.txt"
    if not sp.exists():
        return None, "Generate a brief first."
    cfg["tts"]["voice"] = voice
    cfg["tts"]["speed"] = float(speed)
    cfg["tts"].setdefault("master", {})["enabled"] = bool(master_on)
    meta = _read_meta(script_dir, "brief", "SCALE Brief")
    out = produce_audio(cfg, sp.read_text(encoding="utf-8"), meta)
    return str(out), f"Rendered → {out}"


def library_view():
    from .pipeline import library_summary

    counts, q = library_summary()
    lines = [f"{sum(counts.values())} concepts across {len(counts)} book(s) in the library:", ""]
    for b, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {c:3}  {b}")
    lines.append("")
    lines.append(f"Vector DB (Qdrant): {q if q is not None else 'unavailable'} vectors indexed")
    return "\n".join(lines)


def pending_view():
    from .pipeline import pending_books

    p = pending_books()
    if not p:
        return "(none — every book in data/books/ is ingested)"
    return "Not yet ingested — click Sync to add:\n" + "\n".join(f"  • {x}" for x in p)


def list_books():
    bd = ROOT / load_config()["ingest"]["book_dir"]
    books = [p.name for p in sorted(bd.glob("*")) if p.suffix.lower() in (".pdf", ".epub", ".txt")]
    return "\n".join(books) or "(no books in data/books/)"


def upload_book(file):
    if not file:
        return "No file."
    bd = ROOT / load_config()["ingest"]["book_dir"]
    bd.mkdir(parents=True, exist_ok=True)
    dest = bd / Path(file.name).name
    shutil.copy(file.name, dest)
    os.chmod(dest, 0o644)  # readable on the host too (container runs as root)
    return f"Added {dest.name}. (Note: a new book needs a source profile — see ARCHITECTURE.md.)"


def settings_text():
    cfg = load_config()
    llm = cfg["llm"]
    key_env = llm.get("api_key_env", "OPENROUTER_API_KEY")
    key = "set ✓" if os.environ.get(key_env) else f"MISSING — add {key_env} to .env"
    models = "\n  ".join(llm["models"])
    return (f"LLM provider: {llm.get('provider')}  ({llm.get('base_url')})\n"
            f"{key_env}: {key}\nFree-only guard: {llm.get('free_only')}\n"
            f"Kokoro: {_kokoro_base(cfg)}\nModels (rotation):\n  {models}")


# ---- app -------------------------------------------------------------------

def launch_ui(share=False):
    import gradio as gr

    voices = get_voices()
    with gr.Blocks(title="SCALE", theme=gr.themes.Soft()) as app:
        gr.Markdown("# SCALE — Synthesized Contextual Audio Learning Engine")
        with gr.Tab("1 · Brief — your situation"):
            gr.Markdown(
                "Describe what you're dealing with. SCALE finds the concepts across the "
                "library that fit *you*, packs them to your time, and writes a bespoke briefing."
            )
            need = gr.Textbox(label="Your situation", lines=3,
                              placeholder="e.g. Clients keep asking for free advice and never commit to paying…")
            minutes = gr.Slider(5, 30, value=15, step=1, label="Length (minutes)")
            bgen = gr.Button("Find concepts & write my briefing", variant="primary")
            matched = gr.Markdown()
            brief_script = gr.Textbox(label="Your briefing", lines=14)
            bgen.click(generate_brief, [need, minutes], [matched, brief_script])

            gr.Markdown("### Voice & audio")
            with gr.Row():
                bvoice = gr.Dropdown(voices, value=voices[0], label="Voice / blend")
                bspeed = gr.Slider(0.7, 1.1, value=0.85, step=0.01, label="Speed")
                bmaster = gr.Checkbox(value=True, label="Master (deep/bassy)")
            brender = gr.Button("Render audio", variant="primary")
            baudio = gr.Audio(label="Briefing audio", type="filepath")
            bstatus = gr.Markdown()
            brender.click(render_brief, [bvoice, bspeed, bmaster], [baudio, bstatus])

        with gr.Tab("2 · Context"):
            gr.Markdown("Build/enrich your profile through a short interview.")
            chat = gr.Chatbot(height=360)   # Gradio 5.x: messages format is the default
            cstate = gr.State({})
            msg = gr.Textbox(placeholder="Your answer…", label="")
            with gr.Row():
                start = gr.Button("Start / Restart interview")
            start.click(ctx_start, outputs=[chat, cstate])
            msg.submit(ctx_respond, [msg, chat, cstate], [chat, cstate]).then(lambda: "", None, msg)

        with gr.Tab("3 · Profile"):
            ptext = gr.Code(value=profile_text(), language="yaml", label="config/profile.yaml")
            with gr.Row():
                pload = gr.Button("Reload"); psave = gr.Button("Save", variant="primary")
                pval = gr.Button("Validate")
            pstatus = gr.Markdown()
            pload.click(profile_text, outputs=ptext)
            psave.click(profile_save, ptext, pstatus)
            pval.click(profile_validate, outputs=pstatus)

        with gr.Tab("4 · Library & Settings"):
            gr.Markdown("### Ingested library — what's available for briefings")
            libview = gr.Code(value=library_view(), label="ingested books + vector count")
            librefresh = gr.Button("Refresh")

            gr.Markdown("### Pending ingestion")
            pendview = gr.Code(value=pending_view(), label="in data/books/ but not yet ingested")
            syncbtn = gr.Button("⟳ Sync library (ingest pending books)", variant="primary")
            syncstatus = gr.Markdown()

            def _sync(progress=gr.Progress()):
                from .pipeline import sync_books
                progress(0.0, desc="scanning for new books…")

                def cb(done, total, title, book):
                    progress(done / max(total, 1), desc=f"{book[:18]} · {title[:30]} ({done}/{total})")

                pending, results = sync_books(on_progress=cb)
                msg = ("**Synced:**\n" + "\n".join(f"- {r}" for r in results)) if results \
                    else "Nothing pending — all books already ingested."
                return library_view(), pending_view(), msg

            librefresh.click(lambda: (library_view(), pending_view()), outputs=[libview, pendview])
            syncbtn.click(_sync, outputs=[libview, pendview, syncstatus])

            gr.Markdown("### Add a book")
            up = gr.File(label="Upload (pdf/epub/txt) — then click Sync above to ingest it")
            upstatus = gr.Markdown()
            up.upload(upload_book, up, upstatus).then(pending_view, None, pendview)

            gr.Markdown("### Settings")
            gr.Code(value=settings_text(), label="status")

    app.launch(server_name="0.0.0.0", server_port=7860, share=share)
