"""Concept library — the canonical, tagged store of extracted concepts (Phase 1).

Promotes the grounded concepts (cached in data/extracted/) into a permanent,
per-book library with metadata. This is the source of truth the vector index points
back to. Markdown/JSON here; embeddings live in Qdrant.
"""

import json
import logging

from .config import ROOT, load_config, load_source
from .ingest import slugify

log = logging.getLogger("cale.library")


def book_id(source):
    return slugify(source.get("title", "book"))


def library_dir(source):
    return ROOT / "library" / book_id(source)


def build_library(source=None):
    """Promote a book's cached concepts into library/<book-id>/<slug>.json."""
    cfg = load_config()
    source = source if source is not None else load_source()
    cache = ROOT / cfg["ingest"]["cache_dir"] / book_id(source)
    out = library_dir(source)
    out.mkdir(parents=True, exist_ok=True)

    cat_of, title_of = {}, {}
    for c in source["categories"]:
        for g in (c.get("units") or c.get("games") or []):
            cat_of[slugify(g)] = c["name"]
            title_of[slugify(g)] = g          # canonical, clean title

    n = 0
    for f in sorted(cache.glob("*.json")):
        data = json.loads(f.read_text())
        slug = data.get("slug") or f.stem
        rec = {
            "id": f"{book_id(source)}:{slug}",
            "slug": slug,
            "title": title_of.get(slug) or data.get("title"),
            "book": source["title"],
            "author": source["author"],
            "category": data.get("category") or cat_of.get(slug, ""),
            "unit_label": source.get("unit_label", "concept"),
            "mechanism": data.get("mechanism", ""),
            "explanation": data.get("explanation", ""),
            "quotes": data.get("quotes", []),
        }
        (out / f"{slug}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
        n += 1
    log.info("library: wrote %d concepts -> %s", n, out)
    return out, n


def iter_library():
    """Yield every concept record across all books in the library."""
    base = ROOT / "library"
    if not base.exists():
        return
    for f in sorted(base.glob("*/*.json")):
        yield json.loads(f.read_text())


def embed_text(rec):
    """The text that represents a concept for semantic retrieval."""
    parts = [rec.get("title", ""), rec.get("category", ""),
             rec.get("mechanism", ""), rec.get("explanation", "")]
    return "\n".join(p for p in parts if p)
