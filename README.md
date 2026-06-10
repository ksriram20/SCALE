# SCALE — Synthesized Contextual Audio Learning Engine

Describe a situation you're facing. SCALE pulls the few best-fitting ideas from a
curated, multi-book library, grounds and localizes them to *you*, and speaks them as a
short, magnetic audio briefing — in a deep mastered voice over a soft ambient bed.
Local and free by default.

It's the honest, personal answer to the AI-slop "psychology" channels: every concept is
**explained from the real source and cited**, the application is **anchored to the
concept's actual mechanism** and your real situation, and a **faithfulness auditor**
gates every one before it's spoken. (Product = **SCALE**, command = `scale`, package = `cale`.)

> Architecture & design: see [ARCHITECTURE.md](ARCHITECTURE.md).

## What it does

- **Brief (the main thing):** your situation + a length → the matcher finds the best
  concepts across the *whole library*, writes a grounded, localized, audited script with
  a hook open and deliberate pauses, and renders it. `scale brief "<situation>" --minutes 15`
- **Studio:** walk one book by category. `scale run --episode N`
- **Context:** build your profile through a short conversation. `scale context`
- **Library:** drop books in, `scale sync`, and they're searchable. PDF *and* EPUB.

## Quick start (Docker)

```bash
cp .env.example .env          # add a free OpenRouter key (openrouter.ai/keys)
docker compose up -d qdrant kokoro     # vector DB + local TTS
docker compose build scale ui

# 1) tell it who you are
docker compose run --rm scale context        # or use the UI

# 2) add books (drop PDFs/EPUBs in data/books/, then:)
docker compose run --rm scale sync           # ingest everything not yet indexed
docker compose run --rm scale library        # see what's in the DB

# 3) get a briefing for your situation
docker compose run --rm scale brief "my co-founder keeps overruling me in front of the team" --minutes 12
```

Or just use the **web UI**:
```bash
docker compose up -d --build ui    # http://localhost:7860
```
Tabs: **Context** (interview) · **Profile** · **Brief** (situation → episode) ·
**Studio** (by book) · **Library & Settings** (upload, **Sync** with a progress bar,
voice/pace, what's indexed).

## Commands

| Command | What |
|---|---|
| `scale brief "<situation>" [--minutes N \| --words N] [--no-audio]` | bespoke episode for your situation |
| `scale run --episode N [--games ...] [--no-audio]` | walk a book category |
| `scale context` | conversational profile builder |
| `scale add-book "<file>"` | profile + extract + index one book (EPUB native, PDF LLM-profiled) |
| `scale sync` | ingest every book in `data/books/` not yet in the library |
| `scale library` | concepts per book + Qdrant vector count |
| `scale search "<query>"` | semantic search over the library |
| `scale render --brief \| --episode N` | (re)render an existing script — no LLM |
| `scale persona show\|validate\|edit` · `scale skills list` · `scale report --episode N` | inspect |
| `scale ui` | launch the web UI |

## Length: cap by time *or* words

A brief is capped by **either** `--minutes` **or** `--words`. One target (calibrated at
~150 wpm for the slow, paused voice) flows through the concept count, per-concept depth,
and the polish word-bound — so the whole script flexes. 5 min → fewer/shorter, 30 min →
more/deeper, never padded.

## Configuration (`config/config.yaml`)

- `llm.models` — OpenRouter `:free` rotation; `free_only: true` refuses paid models.
- `episode.words_per_minute`, `concept_words`, `application_words`, `polish` (Narration Director).
- `tts.voice` — single id or a **blend** like `am_onyx(0.7)+am_adam(0.3)`; `speed` (0.85 = slow/deep).
- `tts.master` — `pitch_down_pct`, `bass_gain_db`, `output_format` (wav/mp3 320k).
- `tts.music` — ambient bed from `assets/music/`: `gain_db`, `lowpass_hz` (softness), `duck`, `track`.
- `tts.pauses` — structural beats + `micro` (real in-line silence after enumeration
  numbers, before your name, after questions; Kokoro's punctuation is too faint, so we
  insert silence explicitly via `[[pause:N]]`). The Narration Director also writes for the
  ear — spoken enumeration, tricolon, anaphora, emphasis-by-position. All tunable.

Your persona is `config/profile.yaml`; per-book profiles live in `config/sources/`.

## How grounding is enforced

The intelligence lives in versioned, model-agnostic **skill documents** under `skills/`
(not Python), so you tune the product by editing markdown. Hot-path skills are kept lean
to cut LLM load. The pipeline: extract (cited) → synthesize (mechanism-anchored, localized)
→ **audit** (regenerate on drift) → assemble → Narration Director (craft, never facts) →
breathe → TTS → master. `scale report` surfaces the auditor's per-concept verdict.

## Notes & limitations

- **Music:** tracks in `assets/music/` (`CREDITS.md` has licenses). Personal use is fine;
  if you publish, prefer CC0. Bed is low-passed + ducked to sit soft behind the voice.
- **Scanned PDFs** (no text layer) need OCR first; EPUB is the cleaner format.
- **Copyright:** built for *personal, non-distributed* use of books you own.
- **GPU:** the compose file uses CPU Kokoro; swap to the GPU image for faster TTS.

---

## Reference (auto-generated — do not edit between the markers)

> These sections are regenerated from the code by `tools/sync_docs.py` (run on every
> change via a Claude Code Stop hook). Run `scale <command> -h` for a command's options.

### Commands
<!-- AUTO:commands -->
| Command | What |
|---|---|
| `scale run` | build (and render) an episode |
| `scale ui` | launch the web UI (Gradio) on http://localhost:7860 |
| `scale context` | run a short LLM interview to build/enrich your profile |
| `scale render` | render an existing script to audio (no LLM) |
| `scale extract-all` | extract (cache) every concept in every known book — no audio |
| `scale index` | build all book libraries and index them into Qdrant |
| `scale add-book` | profile a new book (LLM), extract it, and index it |
| `scale sync` | ingest any books in data/books/ not yet in the library |
| `scale library` | show what's in the concept library / vector DB |
| `scale search` | semantic search over the concept library |
| `scale brief` | build a bespoke episode for your situation (Phase 3) |
| `scale list` | list the source book's categories and units |
| `scale persona` | view / validate / edit your static profile |
| `scale skills` | inspect and lint the skill documents |
| `scale report` | show the faithfulness report for an episode |
<!-- /AUTO:commands -->

### Skills (the harness intelligence, in `skills/`)
<!-- AUTO:skills -->
- **application-synthesis** — Map a concept's mechanism onto the user's real situation as one specific, mechanism-driven move — recognize the patte…
- **book-profiler** — Read a book's front matter / table of contents and produce a segmentation profile — its concept units (usually chapte…
- **concept-extraction** — Extract a single concept/unit from a source book grounded ONLY in the provided text, with verbatim citations and the…
- **concept-matching** — From a shortlist of candidate concepts retrieved for a person's situation, select and order the few that genuinely fi…
- **context-interview** — Conduct a short, sharp interview that starts from a blank slate — name, then what they do, then where — and builds a…
- **faithfulness-audit** — Audit a generated concept + application for two failures — concept drift from the source, and application drift into…
- **persona-modeling** — How to read the user's static profile and pick the single most leverageable challenge to anchor a law's application
- **script-assembly** — Re-voice an assembled, grounded briefing into a magnetic spoken-word narration — hook cold-open, rhythmic delivery, i…
<!-- /AUTO:skills -->

### Source modules (`src/cale/`)
<!-- AUTO:modules -->
- `cli.py` — Command-line entry point.
- `config.py` — Configuration and environment loading.
- `context_engine.py` — Conversational context engine — an LLM interview that builds/enriches the profile.
- `embed.py` — Local embeddings via fastembed — CPU, free, no API. Lazy-imported so the rest
- `extract.py` — Phase 1 — extract a unit as a grounded concept (faithful + cited).
- `ingest.py` — Read a source book and segment it into concept units.
- `library.py` — Concept library — the canonical, tagged store of extracted concepts (Phase 1).
- `llm.py` — OpenRouter chat client with free-model rotation and rate-limit handling.
- `master.py` — Audio mastering — the 'deep, bassy, broadcast' sound + an optional music bed.
- `matcher.py` — Phase 3 — the matcher: a person's situation -> the best-fitting concepts.
- `pipeline.py` — End-to-end orchestration: book -> grounded concept -> application -> audit -> script -> audio.
- `report.py` — Faithfulness report — surfaces the auditor's per-law verdict for an episode.
- `script_builder.py` — Phase 4a — assemble grouped law segments into one episode script.
- `skills.py` — Load skill documents — the externalised intelligence of the pipeline.
- `synthesize.py` — Phase 2 — synthesize the persona-specific application of a concept.
- `tts.py` — Kokoro TTS client (local container, OpenAI-compatible /audio/speech).
- `ui.py` — Temporary SCALE UI (Gradio).
- `vectorstore.py` — Qdrant vector store wrapper (lazy-imported).
- `verify.py` — Phase 3 — faithfulness auditor.
<!-- /AUTO:modules -->

