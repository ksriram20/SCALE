"""Command-line entry point."""

import argparse
import logging
import os
import subprocess

from .config import ROOT, load_config, load_profile, load_source, profile_path, validate_profile
from .ingest import slugify
from .pipeline import build_episode, parse_list
from .skills import iter_skill_names, lint_skill


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="scale",
        description="SCALE — Synthesized Contextual Audio Learning Engine",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="build (and render) an episode")
    run.add_argument("--episode", type=int, default=1, help="episode = category number (see `scale list`)")
    run.add_argument("--games", type=str, help="explicit unit titles/slugs, e.g. 'Rapo,Uproar'")
    run.add_argument("--no-audio", action="store_true", help="script only, skip TTS")

    sub.add_parser("ui", help="launch the web UI (Gradio) on http://localhost:7860")
    sub.add_parser("context", help="run a short LLM interview to build/enrich your profile")

    rnd = sub.add_parser("render", help="render an existing script to audio (no LLM)")
    rnd.add_argument("--episode", type=int, default=1)
    rnd.add_argument("--brief", action="store_true", help="render output/scripts/brief.txt instead")

    sub.add_parser("extract-all", help="extract (cache) every concept in every known book — no audio")
    sub.add_parser("index", help="build all book libraries and index them into Qdrant")

    ab = sub.add_parser("add-book", help="profile a new book (LLM), extract it, and index it")
    ab.add_argument("file", help="filename (or part of it) in data/books/")

    sub.add_parser("sync", help="ingest any books in data/books/ not yet in the library")
    sub.add_parser("library", help="show what's in the concept library / vector DB")

    se = sub.add_parser("search", help="semantic search over the concept library")
    se.add_argument("query")
    se.add_argument("--top-k", type=int, default=5)

    br = sub.add_parser("brief", help="build a bespoke episode for your situation (Phase 3)")
    br.add_argument("need", help="your situation, in your words")
    br.add_argument("--minutes", type=int, default=15, help="length cap by time")
    br.add_argument("--words", type=int, help="length cap by word count (overrides --minutes)")
    br.add_argument("--no-audio", action="store_true")

    sub.add_parser("list", help="list the source book's categories and units")

    persona = sub.add_parser("persona", help="view / validate / edit your static profile")
    persona.add_argument("action", nargs="?", default="show",
                         choices=["show", "path", "validate", "edit"])

    skills = sub.add_parser("skills", help="inspect and lint the skill documents")
    skills.add_argument("action", nargs="?", default="list", choices=["list"])

    report = sub.add_parser("report", help="show the faithfulness report for an episode")
    report.add_argument("--episode", type=int, default=1)

    args = parser.parse_args()

    if args.cmd == "run":
        games = parse_list(args.games) if args.games else None
        build_episode(args.episode, games=games, render=not args.no_audio)
    elif args.cmd == "ui":
        from .ui import launch_ui
        launch_ui()
    elif args.cmd == "context":
        from .context_engine import run_interview
        run_interview()
    elif args.cmd == "render":
        if args.brief:
            from .pipeline import render_brief_file
            render_brief_file()
        else:
            from .pipeline import render_episode
            render_episode(args.episode)
    elif args.cmd == "extract-all":
        from .pipeline import extract_all
        ok, failed = extract_all()
        print(f"extracted {ok} concepts; {len(failed)} failed: {failed}")
    elif args.cmd == "index":
        _index()
    elif args.cmd == "add-book":
        from .pipeline import add_book
        source, n, ok, failed = add_book(args.file)
        print(f"\nadded '{source['title']}' by {source['author']}: {n} units, "
              f"{ok} extracted, {len(failed)} failed{(' — ' + str(failed)) if failed else ''}")
    elif args.cmd == "sync":
        from .pipeline import sync_books
        pending, results = sync_books()
        if not pending:
            print("nothing to sync — all books already ingested")
        for r in results:
            print(" ", r)
    elif args.cmd == "library":
        _library()
    elif args.cmd == "search":
        _search(args.query, args.top_k)
    elif args.cmd == "brief":
        from .pipeline import build_custom_episode
        path, chosen = build_custom_episode(args.need, args.minutes, words=args.words, render=not args.no_audio)
        print(f"\nbrief -> {path}\nmatched {len(chosen)} concepts:")
        for c in chosen:
            print(f"  - {c['title']} [{c.get('category')}] — {c.get('why','')}")
    elif args.cmd == "list":
        _list_source()
    elif args.cmd == "persona":
        _persona(args.action)
    elif args.cmd == "skills":
        _skills_list()
    elif args.cmd == "report":
        _report(args.episode)


def _index():
    from .pipeline import reindex_all

    n, count = reindex_all()
    print(f"indexed {count} concepts across all books into 'scale_concepts'")


def _library():
    from .pipeline import library_summary

    counts, qcount = library_summary()
    total = sum(counts.values())
    print(f"Concept library: {total} concepts across {len(counts)} book(s)")
    for book, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:3}  {book}")
    print(f"Vector DB (Qdrant 'scale_concepts'): {qcount if qcount is not None else 'unavailable'} vectors")


def _search(query, top_k):
    from .embed import embed
    from .vectorstore import search

    qvec = embed([query])[0]
    results = search(qvec, top_k)
    if not results:
        print("no results (did you run `scale index`?)")
        return
    print(f"top {len(results)} for: {query!r}\n")
    for score, p in results:
        print(f"  {score:.3f}  {p.get('title')}  [{p.get('category')}] — {p.get('book')}")


def _list_source():
    source = load_source()
    print(f"{source['title']} — {source['author']}  (unit: {source['unit_label']})\n")
    for i, cat in enumerate(source["categories"], 1):
        print(f"Episode {i}: {cat['name']}  ({len(cat['games'])} {source['unit_label_plural']})")
        for g in cat["games"]:
            print(f"    - {g}   [{slugify(g)}]")
        print()


def _persona(action):
    path = profile_path()
    if action == "path":
        print(path)
        return
    if action == "edit":
        editor = os.environ.get("EDITOR", "nano")
        subprocess.call([editor, str(path)])
        return

    profile = load_profile()
    if action == "validate":
        problems = validate_profile(profile)
        print("profile OK" if not problems else "profile issues:")
        for p in problems:
            print(f"  - {p}")
        return

    print(f"# {path}\n")
    print(f"name:   {profile.get('name')}")
    print(f"role:   {profile.get('role')}")
    print(f"domain: {profile.get('domain')}")
    for key in ("goals", "challenges"):
        items = profile.get(key) or []
        if items:
            print(f"{key}:")
            for it in items:
                print(f"  - {it}")


def _skills_list():
    names = iter_skill_names()
    if not names:
        print("no skills found under skills/")
        return
    total = 0
    for name in names:
        info, warnings = lint_skill(name)
        total += len(warnings)
        status = "ok" if not warnings else f"{len(warnings)} warning(s)"
        print(f"\n{info['name']}  [{status}]")
        print(f"  {info['description']}")
        if info["fields"]:
            print(f"  input fields: {', '.join(info['fields'])}")
        if info["companions"]:
            print(f"  companions:   {', '.join(info['companions'])}")
        for w in warnings:
            print(f"  ! {w}")
    print(f"\n{len(names)} skill(s), {total} warning(s).")


def _report(episode_number):
    cfg = load_config()
    report_dir = ROOT / cfg["output"].get("report_dir", "output/reports")
    path = report_dir / f"episode_{episode_number:02d}.md"
    if not path.exists():
        print(f"no report yet for episode {episode_number} (run it first): {path}")
        return
    print(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
