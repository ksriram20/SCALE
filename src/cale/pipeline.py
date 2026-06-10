"""End-to-end orchestration: book -> grounded concept -> application -> audit -> script -> audio.

Book-agnostic: the source work and its segmentation/episode structure are defined
in config/source.yaml. An episode maps to one category of units.
"""

import datetime
import json
import logging
import re
from pathlib import Path

from .config import ROOT, load_all_sources, load_config, load_profile, load_source
from .extract import extract_concept
from .ingest import read_book, segment
from .llm import OpenRouterClient
from .script_builder import breathe, build_episode_script, persona_to_text, polish_script, word_count
from .synthesize import synthesize_application
from .tts import KokoroClient
from .verify import verify

log = logging.getLogger("cale.pipeline")


def find_book(cfg, source):
    book_dir = ROOT / cfg["ingest"]["book_dir"]
    fname = source.get("file")
    if fname:
        p = book_dir / fname
        if p.exists():
            return p
        log.warning("source.file '%s' not found — using first book in %s", fname, book_dir)
    books = [p for p in sorted(book_dir.glob("*")) if p.suffix.lower() in (".pdf", ".epub", ".txt")]
    if not books:
        raise FileNotFoundError(f"put a .pdf/.epub/.txt book in {book_dir}")
    return books[0]


def build_episode(episode_number, games=None, render=True):
    cfg = load_config()
    profile = load_profile()
    source = load_source()
    llm = OpenRouterClient(cfg)
    persona_text = persona_to_text(profile)
    domain = profile.get("domain", "your work")
    locale = profile.get("country", "")

    log.info("reading %s", find_book(cfg, source).name)
    units = segment_book(cfg, source)

    if games:
        wanted = {g.strip().lower() for g in games}
        selected = [u for u in units if u["slug"] in wanted or u["title"].lower() in wanted]
        if not selected:
            raise SystemExit(f"no units matched {sorted(wanted)} — try `scale list`")
        category = selected[0]["category"]
        label = "selection: " + ", ".join(u["title"] for u in selected)
    else:
        cats = source["categories"]
        if not (1 <= episode_number <= len(cats)):
            raise SystemExit(f"episode {episode_number} out of range 1..{len(cats)} (see `scale list`)")
        category = cats[episode_number - 1]["name"]
        selected = [u for u in units if u["category"] == category]
        label = category
    log.info("episode %d -> %s (%d units)", episode_number, label, len(selected))

    segments = []
    for u in selected:
        concept = extract_concept(llm, cfg, source, u)
        application = synthesize_application(llm, cfg, source, concept, persona_text, domain, locale)

        audit, regens = None, 0
        if cfg["verify"]["enabled"]:
            for _ in range(cfg["verify"]["max_regenerations"] + 1):
                audit = verify(llm, cfg, source, u["text"], concept, application)
                if audit.get("concept_faithful") and audit.get("application_grounded"):
                    break
                regens += 1
                log.warning("%s faithfulness issues: %s", u["title"], audit.get("issues"))
                application = synthesize_application(llm, cfg, source, concept, persona_text, domain, locale)

        segments.append(
            {"concept": concept, "application": application, "audit": audit, "regens": regens}
        )

    script = build_episode_script(profile, source, category, segments, pauses=cfg["tts"].get("pauses"),
                                  with_recap=cfg["episode"].get("recap", True))
    if cfg["episode"].get("polish"):
        log.info("polishing script (narration director)")
        script = polish_script(llm, cfg, script)
    if (cfg["tts"].get("pauses") or {}).get("micro", True):
        script = breathe(script, profile.get("name", ""))

    script_dir = ROOT / cfg["output"]["script_dir"]
    script_dir.mkdir(parents=True, exist_ok=True)
    base = f"episode_{episode_number:02d}"
    script_path = script_dir / f"{base}.txt"
    script_path.write_text(script, encoding="utf-8")
    _share(script_path)
    log.info("script -> %s (%d words)", script_path, word_count(script))

    meta = {
        "stem": _safe(f"{source['title']} - {category}"),
        "title": f"{category} — {source['title']}",
        "artist": f"{source.get('author', '')} · SCALE".strip(" ·"),
        "album": f"{source['title']} · SCALE",
        "date": _year(), "genre": "Education",
        "comment": f"SCALE briefing for {profile.get('name', 'listener')}",
    }
    _write_meta(script_dir, base, meta)

    if cfg["verify"]["enabled"]:
        from .report import write_report

        write_report(cfg, episode_number, category, segments)

    if render:
        produce_audio(cfg, script, meta)

    return script_path


def _safe(name):
    """Filesystem-safe, human-readable filename base."""
    name = re.sub(r"[\\/:*?\"<>|]+", " ", str(name))
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120] or "episode"


def _year():
    return datetime.date.today().strftime("%Y")


def _share(path):
    """Make a container-written file host-readable AND host-overwritable (0666),
    so files written as root in mounted volumes don't lock the host out."""
    try:
        Path(path).chmod(0o666)
    except OSError:
        pass
    return path


_PAUSE_RE = re.compile(r"\[\[pause(?::([0-9.]+))?\]\]")


def render_speech(cfg, text, out_path):
    """Render speech, turning visible [[pause:N]] markers into real silence by
    splitting the text, synthesizing each chunk, and concatenating with silence."""
    import shutil
    import subprocess

    out_path = Path(out_path)
    tts = KokoroClient(cfg)
    if not _PAUSE_RE.search(text):
        return tts.synthesize(text, out_path)
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg missing — rendering without pauses")
        return tts.synthesize(_PAUSE_RE.sub(" ", text), out_path)

    default_dur = ((cfg.get("tts") or {}).get("pauses") or {}).get("default", 0.8)
    segdir = out_path.parent / f"{out_path.stem}.segs"
    segdir.mkdir(parents=True, exist_ok=True)
    parts = _PAUSE_RE.split(text)   # [text, dur, text, dur, ..., text]
    segs, n_pause = [], 0
    for j, part in enumerate(parts):
        if j % 2 == 0:
            chunk = (part or "").strip()
            if chunk:
                seg = segdir / f"s{len(segs):03d}.wav"
                tts.synthesize(chunk, seg)
                segs.append(seg)
        else:
            dur = float(part) if part else default_dur
            seg = segdir / f"s{len(segs):03d}.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                            "-i", "anullsrc=r=24000:cl=mono", "-t", str(dur),
                            "-ar", "24000", "-ac", "1", str(seg)], check=True)
            segs.append(seg)
            n_pause += 1
    listfile = segdir / "list.txt"
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in segs))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listfile), "-ar", "24000", "-ac", "1", str(out_path)], check=True)
    shutil.rmtree(segdir, ignore_errors=True)
    log.info("rendered with %d pause(s)", n_pause)
    return out_path


def produce_audio(cfg, script, meta):
    """Render `script` to audio with a descriptive name + embedded tags.
    `meta` = {stem, title, artist, album, date, genre, comment}. Returns the path."""
    from .master import master_audio

    audio_dir = ROOT / cfg["output"]["audio_dir"]
    audio_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe(meta.get("stem") or meta.get("title") or "episode")
    tts_cfg = cfg.get("tts", {})
    master_on = bool((tts_cfg.get("master") or {}).get("enabled"))
    raw_fmt = tts_cfg.get("format", "mp3")

    if master_on:
        raw = audio_dir / f"{stem}.raw.{raw_fmt}"
        render_speech(cfg, script, raw)
        final_fmt = (tts_cfg.get("master") or {}).get("output_format", raw_fmt)
        out = master_audio(raw, audio_dir / f"{stem}.{final_fmt}", cfg, meta=meta)
        try:
            raw.unlink()   # drop the unmastered intermediate
        except OSError:
            pass
        return _share(out)

    final = audio_dir / f"{stem}.{raw_fmt}"
    render_speech(cfg, script, final)
    return _share(final)


def _write_meta(script_dir, base, meta):
    p = script_dir / f"{base}.meta.json"
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    _share(p)


def _read_meta(script_dir, base, default_stem):
    p = script_dir / f"{base}.meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"stem": default_stem}


def render_brief_file():
    """Render the latest custom brief (output/scripts/brief.txt) to audio."""
    cfg = load_config()
    script_dir = ROOT / cfg["output"]["script_dir"]
    sp = script_dir / "brief.txt"
    if not sp.exists():
        raise SystemExit("no brief.txt yet — run `scale brief \"<situation>\"` first")
    meta = _read_meta(script_dir, "brief", "SCALE Brief")
    out = produce_audio(cfg, sp.read_text(encoding="utf-8"), meta)
    log.info("audio -> %s", out)
    return out


def render_episode(episode_number):
    """Render an already-generated episode script to audio — no LLM calls."""
    cfg = load_config()
    script_path = ROOT / cfg["output"]["script_dir"] / f"episode_{episode_number:02d}.txt"
    if not script_path.exists():
        raise SystemExit(f"no script for episode {episode_number} — run it first: {script_path}")
    script_dir = ROOT / cfg["output"]["script_dir"]
    meta = _read_meta(script_dir, f"episode_{episode_number:02d}", f"episode_{episode_number:02d}")
    audio_path = produce_audio(cfg, script_path.read_text(encoding="utf-8"), meta)
    log.info("audio -> %s", audio_path)
    return audio_path


def build_custom_episode(need, minutes=15, words=None, render=True):
    """Phase 3: a bespoke episode for a person's situation — matched, not book-walked.
    Length is capped by EITHER minutes or words; one derived target flows to the
    concept count and the polish word-bound, so the script genuinely flexes."""
    from .matcher import match
    from .script_builder import build_custom_script

    cfg = load_config()
    profile = load_profile()
    source = load_source()
    llm = OpenRouterClient(cfg)

    ep = cfg["episode"]
    wpm = ep.get("words_per_minute", 150)
    per_concept = ep.get("concept_words", 150) + ep.get("application_words", 380)
    target_words = int(words) if words else int(minutes * wpm)
    target_k = max(1, round(target_words / per_concept))
    cfg["episode"]["target_words"] = [int(target_words * 0.9), int(target_words * 1.1)]
    log.info("length target: ~%d words (~%.0f min, %d concepts)", target_words, target_words / wpm, target_k)

    persona_text = persona_to_text(profile)
    domain = profile.get("domain", "your work")
    locale = profile.get("country", "")
    stance = source.get("application_stance", "both")

    chosen = match(need, profile, target_k)
    if not chosen:
        raise SystemExit("no matching concepts found — try rephrasing, or run `scale index`")

    segments = []
    for rec in chosen:
        concept = {
            "title": rec["title"], "mechanism": rec["mechanism"],
            "explanation": rec["explanation"], "category": rec.get("category", ""),
        }
        rec_source = {
            "title": rec["book"], "author": rec["author"],
            "unit_label": rec.get("unit_label", "concept"), "application_stance": stance,
        }
        application = synthesize_application(llm, cfg, rec_source, concept, persona_text, domain, locale)
        if cfg["verify"]["enabled"]:
            for _ in range(cfg["verify"]["max_regenerations"] + 1):
                audit = verify(llm, cfg, rec_source, rec["explanation"], concept, application)
                if audit.get("concept_faithful") and audit.get("application_grounded"):
                    break
                application = synthesize_application(llm, cfg, rec_source, concept, persona_text, domain, locale)
        segments.append({"concept": concept, "application": application})

    script = build_custom_script(profile, need, segments, pauses=cfg["tts"].get("pauses"),
                                 with_recap=cfg["episode"].get("recap", True))
    if cfg["episode"].get("polish"):
        script = polish_script(llm, cfg, script)
    if (cfg["tts"].get("pauses") or {}).get("micro", True):
        script = breathe(script, profile.get("name", ""))
    script_dir = ROOT / cfg["output"]["script_dir"]
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / "brief.txt"
    script_path.write_text(script, encoding="utf-8")
    _share(script_path)
    log.info("brief -> %s (%d words; %d concepts)", script_path, word_count(script), len(segments))

    topic = _safe(need)[:48]
    today = datetime.date.today().strftime("%Y-%m-%d")
    meta = {
        "stem": _safe(f"SCALE Brief {today} - {topic}"),
        "title": f"SCALE Brief: {topic}",
        "artist": "SCALE", "album": "SCALE Briefings",
        "date": _year(), "genre": "Education",
        "comment": need[:240],
    }
    _write_meta(script_dir, "brief", meta)

    if render:
        produce_audio(cfg, script, meta)
    return script_path, chosen


def segment_book(cfg, source):
    """Segment a book into units, using the native EPUB path when applicable."""
    path = find_book(cfg, source)
    if source.get("segmentation", {}).get("method") == "epub_toc" or path.suffix.lower() == ".epub":
        from .ingest import units_from_epub
        cat = source["categories"][0]["name"] if source.get("categories") else source.get("title", "")
        return units_from_epub(path, category=cat)
    return segment(read_book(path), source)


def _extract_book(llm, cfg, source, on_progress=None):
    """Resilient extraction of every unit in one book. Returns (ok, [failed]).
    `on_progress(done, total, title, book)` is called after each unit (for UI bars)."""
    units = segment_book(cfg, source)
    total = len(units)
    ok, failed = 0, []
    for i, u in enumerate(units, 1):
        try:
            extract_concept(llm, cfg, source, u)  # cache-hit skips the LLM call
            ok += 1
            log.info("[%s] extracted %d/%d: %s", source["title"][:24], i, total, u["title"])
        except Exception as e:  # noqa: BLE001 — keep going through the whole book
            failed.append(u["title"])
            log.warning("[%s] FAILED %s — %s", source["title"][:24], u["title"], e)
        if on_progress:
            on_progress(i, total, u["title"], source["title"])
    return ok, failed


def extract_all():
    """Extract (cache) concepts for EVERY known book — no synthesis/audio.
    Resilient: a failure is skipped, not fatal; cached successes are skipped."""
    cfg = load_config()
    llm = OpenRouterClient(cfg)
    total_ok, all_failed = 0, []
    for source in load_all_sources():
        ok, failed = _extract_book(llm, cfg, source)
        total_ok += ok
        all_failed += [f"{source['title']}: {t}" for t in failed]
    if all_failed:
        log.warning("%d failed (re-run to retry): %s", len(all_failed), all_failed)
    return total_ok, all_failed


def _title_author_from_filename(name):
    stem = name.rsplit(".", 1)[0]
    author = ""
    m = re.search(r"\(([^)]+)\)\s*$", stem)
    if m:
        author = m.group(1).strip()
        stem = stem[: m.start()].strip()
    # trim long subtitle noise: keep up to first " How "/" Notes "/colon
    title = re.split(r"\s+(?:How|Notes|The Psychology)\b|:", stem)[0].strip() or stem[:60]
    return title, author


def add_book(file_arg, do_index=True, on_progress=None):
    """Add a new book: build its source profile (EPUB = native TOC, no LLM; PDF =
    LLM-profiled), extract concepts, build its library, index. Returns
    (source, n_units, ok, failed)."""
    from .skills import load_skill
    from .extract import parse_json
    from .ingest import slugify, units_from_epub
    from .library import build_library
    import yaml as _yaml

    cfg = load_config()
    llm = OpenRouterClient(cfg)
    book_dir = ROOT / cfg["ingest"]["book_dir"]
    matches = [p for p in sorted(book_dir.glob("*"))
               if file_arg.lower() in p.name.lower() and p.suffix.lower() in (".pdf", ".epub", ".txt")]
    if not matches:
        raise SystemExit(f"no book in {book_dir} matching {file_arg!r}")
    path = matches[0]
    title, author = _title_author_from_filename(path.name)

    if path.suffix.lower() == ".epub":
        # Native: chapters straight from the EPUB's own TOC — no LLM, no guessing.
        units = units_from_epub(path, category=title)
        if not units:
            raise SystemExit(f"no chapters found in EPUB {path.name}")
        source = {
            "title": title, "author": author,
            "unit_label": "chapter", "unit_label_plural": "chapters",
            "file": path.name, "application_stance": "both",
            "segmentation": {"method": "epub_toc"},
            "categories": [{"name": title, "units": [u["title"] for u in units]}],
        }
        method = "EPUB TOC (native)"
    else:
        text = read_book(path)
        skill = load_skill("book-profiler")
        raw = llm.chat(skill.system, skill.render_input(title=title, author=author, toc=text[:9000]), json_mode=True)
        prof = parse_json(raw)
        source = {
            "title": title, "author": author,
            "unit_label": prof.get("unit_label", "chapter"),
            "unit_label_plural": prof.get("unit_label_plural", "chapters"),
            "file": path.name, "application_stance": "both",
            "segmentation": {"method": "toc_titles"},
            "categories": [
                {"name": c.get("name", title), "units": c.get("units") or c.get("games") or []}
                for c in prof.get("categories", [])
            ],
        }
        units = segment(text, source)
        method = "LLM profile + toc_titles"

    sdir = ROOT / "config" / "sources"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / f"{slugify(title)}.yaml").write_text(
        _yaml.safe_dump(source, sort_keys=False, allow_unicode=True), encoding="utf-8")
    log.info("profiled '%s' (%s) -> %d units", title, method, len(units))

    ok, failed = _extract_book(llm, cfg, source, on_progress=on_progress)
    build_library(source)
    if do_index:
        reindex_all()
    return source, len(units), ok, failed


def pending_books():
    """Files in data/books/ that are not yet ingested into the library."""
    cfg = load_config()
    book_dir = ROOT / cfg["ingest"]["book_dir"]
    files = [p for p in sorted(book_dir.glob("*")) if p.suffix.lower() in (".pdf", ".epub", ".txt")]
    ingested = set(library_summary()[0].keys())
    return [p.name for p in files if _title_author_from_filename(p.name)[0] not in ingested]


def sync_books(on_progress=None):
    """Ingest every book in data/books/ that isn't in the library yet.
    Returns (pending_names, [result strings])."""
    pending = pending_books()
    results = []
    for name in pending:
        try:
            source, n, ok, failed = add_book(name, do_index=True, on_progress=on_progress)
            results.append(f"{source['title']}: {ok}/{n} chapters ingested"
                           + (f", {len(failed)} failed" if failed else ""))
        except Exception as e:  # noqa: BLE001
            results.append(f"{name}: FAILED ({e})")
            log.warning("sync: %s failed — %s", name, e)
    return pending, results


def reindex_all():
    """Rebuild every book's library and (re)index all concepts into Qdrant."""
    from .library import build_library, iter_library, embed_text
    from .embed import embed, DIM
    from .vectorstore import ensure_collection, upsert

    total = 0
    for source in load_all_sources():
        try:
            _out, n = build_library(source)
            total += n
        except Exception as e:  # noqa: BLE001
            log.warning("library build failed for %s — %s", source.get("title"), e)
    recs = list(iter_library())
    vecs = embed([embed_text(r) for r in recs])
    ensure_collection(DIM)
    count = upsert(recs, vecs)
    log.info("indexed %d concepts across books", count)
    return len(recs), count


def library_summary():
    """(per_book_counts dict, qdrant_count or None) — what's actually in the library/DB."""
    from collections import Counter
    from .library import iter_library

    counts = Counter(r["book"] for r in iter_library())
    qcount = None
    try:
        from .vectorstore import COLLECTION, _client
        qcount = _client().count(COLLECTION).count
    except Exception:  # noqa: BLE001
        pass
    return dict(counts), qcount


def parse_list(spec):
    """'Rapo,Uproar' or 'rapo, the-stocking-game' -> ['Rapo','Uproar']."""
    return [p.strip() for p in spec.split(",") if p.strip()]
