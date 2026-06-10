# SCALE — Architecture

**SCALE — Synthesized Contextual Audio Learning Engine.**
Describe your situation → the engine pulls the best ideas from a curated, multi-book
library → grounds and localizes them to *you* → and speaks them as a short, magnetic
audio briefing. Local and free by default.

> Product name **SCALE**; CLI command `scale`; Python package `cale`.

---

## 1. The product, in one line

> Not "an audiobook that knows your name" — a strategist that reaches into a library
> and pulls the few concepts that fit *your* situation, in the minutes you have.

Two ways to use it:
- **Brief (person-centric, primary):** a situation → matched concepts across the whole
  library → one bespoke episode. `scale brief "<situation>" --minutes 15`
- **Studio (book-centric):** walk one book by category. `scale run --episode N`

---

## 2. The grounding contract (non-negotiable)

This is the moat and the ethic — what separates SCALE from misattributing slop:
- **Concept = faithful + cited.** Explained only from the real source text, with quotes.
- **Application = mechanism-anchored.** A faithful extension of the concept's *actual
  mechanism*, never generic advice. Test: "if the advice works without this concept, it's wrong."
- **Honest attribution.** The real author/book is credited; never faked.
- **Relevance is honest.** Surface only what genuinely fits; never force a concept onto a life.
- **Locale is real.** The person's actual system (e.g. Indian academia: UGC/NAAC/DST-SERB,
  HoD/Dean, CAS) — never a Western default.
- **Zero fluff.** No padding to fill time. Density is a feature.

A **faithfulness auditor** (LLM) gates every concept on the first two before audio.

---

## 3. The pipeline (Brief / person-centric flow)

```
situation + (minutes OR words) + persona
        │
[len]   derive one target → concept count + per-concept depth + polish word-bound
        ▼
[1] RETRIEVE   embed situation → Qdrant top-K candidates (local embeddings)
[2] RE-RANK    LLM judges true fit, discards stretches, diversifies, packs to count
        ▼
[3] per concept (from the library, already extracted):
      SYNTHESIZE  localized, mechanism-anchored application (stance: both/defuse/deploy)
      AUDIT       faithfulness gate → regenerate if it drifts
        ▼
[4] ASSEMBLE   grounded segments → one script (+ structural [[pause]] markers)
[5] NARRATION DIRECTOR (LLM polish)  written-good -> spoken-good: hook open, SPOKEN
                                     ENUMERATION of lists, tricolon, anaphora, emphasis-by-
                                     position, open loops, graded pauses, synthesizing close
                                     — facts/attribution unchanged, no padding
[6] BREATHE    deterministic REAL silence ([[pause]], not faint ellipses) after each
               enumeration number, before the name, after rhetorical questions
        ▼
[7] TTS        Kokoro, deep blended voice, [[pause]] → real silence (split/synth/concat)
[8] MASTER     pitch-down + bass + compression + ducked low-passed music bed + ID3 tags
        ▼
   "<descriptive name>.wav/.mp3"
```

---

## 4. Data model

- **Concept library (canonical):** `library/<book-id>/<slug>.json` — the grounded text
  (title, mechanism, explanation, quotes, book, author, category). Human-readable, the
  source of truth the vector index points back to.
- **Vector index:** Qdrant collection `scale_concepts` — embeddings + the record as payload.
  SCALE's *own isolated* Qdrant (host port 6533, separate volume) — never touches other projects.
- **Embeddings:** local `fastembed` (`bge-small`, CPU, free).
- **Per-book profile:** `config/sources/<book-id>.yaml` (segmentation + categories), plus
  the legacy single `config/source.yaml`. `load_all_sources()` reads them all.
- **Persona:** `config/profile.yaml` — built/enriched by the conversational `scale context`.
- **Skills:** `skills/<name>/SKILL.md` (+ `input.md`) — the versioned, model-agnostic
  intelligence. Hot-path skills are lean (no heavy per-call appends) to cut LLM load.

---

## 5. Components — all built

| Component | How |
|---|---|
| Ingestion — PDF | `pdftotext` + LLM-profiled `toc_titles` segmentation |
| Ingestion — EPUB | **native**: chapters straight from the EPUB's TOC (no LLM, more reliable) |
| Multi-book | `scale add-book`, `scale sync` (drop + ingest), `scale library` view |
| Grounded extraction + faithfulness audit | `concept-extraction`, `faithfulness-audit` skills |
| Conversational context engine | `scale context` (clean-slate, locale-aware interview) |
| Vector retrieval + LLM re-rank (the matcher) | `matcher.py` + `concept-matching` skill |
| Localized, stance-based synthesis | `application-synthesis` skill |
| Narration Director (delivery craft) | `script-assembly` skill |
| Pauses | structural `[[pause:N]]` (split→synth→real silence) + deterministic in-line beats (`breathe`); Kokoro's punctuation is too faint, so silence is inserted explicitly |
| Narration craft | spoken enumeration, tricolon, anaphora, emphasis-by-position, open loops — script-level only (TTS can't do vocal modulation) |
| Length control | cap by minutes **or** words; one target flows everywhere (150 wpm) |
| TTS + mastering | Kokoro deep blend + pitch/bass/compression + ducked low-passed music bed + ID3 tags |
| LLM client | OpenRouter free models, rotation on 429/403/404, free-only guard, lenient JSON |
| UI | Gradio: Context · Profile · Brief · Studio · Library&Settings (Sync + progress) |
| Containers | `kokoro`, `qdrant`, `scale`, `ui` (docker-compose) |

---

## 6. Principles

1. **Faithfulness over fluency.** A hollow-but-smooth episode is failure.
2. **Their craft, our truth.** Borrow the delivery of the best narrators; never their
   misattribution or padding.
3. **Skills hold the intelligence**, in versioned markdown — tune the product by editing
   skills, not code. Keep them tight and model-agnostic.
4. **Reduce LLM load.** Prefer deterministic work (segmentation, pauses, length math,
   filenames) over LLM calls; keep hot-path prompts lean.
5. **Local & free by default.** Free OpenRouter models + local Kokoro + local embeddings;
   paid is opt-in.
6. **Curate deliberately.** A small, well-audited library beats a big noisy one.

---

## 7. Open / next

- Unify the Studio (book-centric) flow under the same length cap.
- Continue the skill-leaning audit across the remaining skills (measure token deltas).
- MP3-320 default + a UI download button; daily scheduling for a fresh commute brief.
- Vector-DB-backed cross-book de-duplication as the library grows.

---

## 8. Reference (auto-generated — do not edit between the markers)

> Regenerated from the repo by `tools/sync_docs.py` (a Claude Code Stop hook runs it
> on every change), so this never drifts from the code.

### Skills (`skills/`)
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
