"""Read a source book and segment it into concept units.

Reading prefers Poppler's `pdftotext` (best text fidelity, ships on most systems
and in our Docker image) with a pypdf fallback. Segmentation is driven entirely by
config/source.yaml so the engine is book-agnostic.

A "unit" is one concept the pipeline will turn into a segment:
    {"index", "number", "category", "title", "slug", "text"}
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("cale.ingest")

# Body heading like "1 ALCOHOLIC" / "12 NOW I'VE GOT YOU" — number + ALL-CAPS title.
# (TOC lines look the same but carry dotted leaders + a page number; we drop those.)
HEAD_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Z][A-Z0-9'’.,?&\- ]{2,45})\s*$")


def read_book(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".epub":
        return _read_epub(path)
    raise ValueError(f"unsupported book format: {suffix}")


def _read_pdf(path):
    if shutil.which("pdftotext"):
        out = subprocess.run(
            ["pdftotext", str(path), "-"], capture_output=True, text=True
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout
        log.warning("pdftotext failed (rc=%s) — falling back to pypdf", out.returncode)
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _read_epub(path):
    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    book = epub.read_epub(str(path))
    parts = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        parts.append(soup.get_text("\n"))
    return "\n".join(parts)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


_EPUB_SKIP = re.compile(
    r"(cover|title\s*page|copyright|^contents$|table of contents|dedication|epigraph|"
    r"acknowledg|about the author|^index$|^notes?$|footnotes|bibliography|references|"
    r"also by|praise|colophon|front ?matter|back ?matter|half title)",
    re.I,
)


def read_epub_chapters(path):
    """Return [(title, text), ...] from an EPUB's own TOC + per-chapter files.

    Uses the book's structure directly — no heading-guessing — so it's far more
    reliable than flattening to text and hunting for chapter headings (the PDF path).
    Front/back matter and tiny sections are filtered out.
    """
    from bs4 import BeautifulSoup
    from ebooklib import epub

    book = epub.read_epub(str(path))

    def text_of(href):
        item = book.get_item_with_href(href.split("#")[0])
        if not item:
            return ""
        return BeautifulSoup(item.get_content(), "html.parser").get_text("\n")

    def flatten(toc):
        out = []
        for t in toc:
            if isinstance(t, tuple):          # (Section, [children])
                out += flatten(t[1])
            else:                             # epub.Link
                out.append(t)
        return out

    chapters, seen = [], set()
    for link in flatten(book.toc):
        title = (getattr(link, "title", "") or "").strip()
        base = (getattr(link, "href", "") or "").split("#")[0]
        if not title or not base or _EPUB_SKIP.search(title) or base in seen:
            continue
        seen.add(base)
        text = text_of(base).strip()
        if len(text.split()) >= 150:          # skip stub/front-matter sections
            chapters.append((title, text))
    return chapters


def units_from_epub(path, category=""):
    units = []
    for k, (title, text) in enumerate(read_epub_chapters(path), 1):
        units.append({
            "index": k, "number": k, "category": category,
            "title": title, "slug": slugify(title), "text": text,
        })
    return units


def _flat_units(source):
    flat = []
    for cat in source["categories"]:
        for title in (cat.get("units") or cat.get("games") or []):
            flat.append((cat["name"], title))
    return flat


def segment(text, source):
    method = source.get("segmentation", {}).get("method", "numbered_caps_headings")
    if method == "numbered_caps_headings":
        return _segment_numbered_caps(text, source)
    if method == "toc_titles":
        return _segment_toc_titles(text, source)
    if method == "law_regex":
        return _segment_law_regex(text, source)
    raise ValueError(f"unknown segmentation method: {method}")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _find_heading(lines, title, cursor):
    """Locate a unit heading in the body at/after `cursor`. Prefers an ALL-CAPS
    standalone line (book chapter headings), then a case-insensitive standalone
    match, then a line ending with the title (e.g. 'Chapter 8. Secrets')."""
    nt = _norm(title)
    if not nt:
        return None
    for want_caps in (True, False):
        for i in range(cursor, len(lines)):
            ln = lines[i].strip()
            if not ln:
                continue
            if want_caps and ln != ln.upper():
                continue
            if _norm(ln) == nt:
                return i
    for i in range(cursor, len(lines)):
        ln = lines[i].strip()
        if len(ln) < len(title) + 16 and _norm(ln).endswith(nt):
            return i
    return None


def _segment_toc_titles(text, source):
    """General segmentation: locate each profile unit-title in the body in order."""
    lines = text.splitlines()
    flat = _flat_units(source)
    cursor, located = 0, []
    for cat, title in flat:
        idx = _find_heading(lines, title, cursor)
        located.append((idx, cat, title))
        if idx is not None:
            cursor = idx + 1
    valid = [(i, c, t) for (i, c, t) in located if i is not None]
    if not valid:
        raise RuntimeError("toc_titles: located 0 unit headings — check the source profile titles")
    units = []
    for k, (i, c, t) in enumerate(valid):
        end = valid[k + 1][0] if k + 1 < len(valid) else min(i + 400, len(lines))
        units.append({
            "index": k + 1, "number": k + 1, "category": c, "title": t,
            "slug": slugify(t), "text": "\n".join(lines[i:end]).strip(),
        })
    log.info("toc_titles: located %d/%d units", len(valid), len(flat))
    return units


def _segment_numbered_caps(text, source):
    """Numbered ALL-CAPS body headings (e.g. Berne's games). The canonical title
    list in source.yaml supplies casing + category; detected heading positions
    supply the boundaries."""
    lines = text.splitlines()
    start_title = source["segmentation"].get("start_title", "").upper()

    heads = [
        (i, m.group(2).strip())
        for i, line in enumerate(lines)
        if i > 40 and ".." not in line and (m := HEAD_RE.match(line))
    ]
    flat = _flat_units(source)
    try:
        start = next(k for k, (_, t) in enumerate(heads) if t.upper() == start_title)
    except StopIteration:
        raise RuntimeError(
            f"start_title '{start_title}' not found among detected headings — "
            "check the book text or source.yaml"
        )

    unit_heads = heads[start : start + len(flat)]
    if len(unit_heads) != len(flat):
        raise RuntimeError(
            f"detected {len(unit_heads)} unit headings but source.yaml lists "
            f"{len(flat)} — segmentation mismatch; inspect the book's headings"
        )

    units = []
    for k, (category, title) in enumerate(flat):
        a = unit_heads[k][0]
        b = unit_heads[k + 1][0] if k + 1 < len(unit_heads) else _next_boundary(lines, a)
        body = "\n".join(lines[a:b]).strip()
        units.append(
            {
                "index": k + 1,
                "number": k + 1,
                "category": category,
                "title": title,
                "slug": slugify(title),
                "text": body,
            }
        )
    log.info("segmented %d units across %d categories", len(units), len(source["categories"]))
    return units


def _next_boundary(lines, start):
    for j in range(start + 1, min(start + 200, len(lines))):
        if re.match(r"^\s*(CHAPTER|PART)\b", lines[j]):
            return j
    return min(start + 120, len(lines))


def _segment_law_regex(text, source):
    """Backward-compat for 'LAW N' books (e.g. Greene's 48 Laws of Power)."""
    pat = re.compile(r"(?m)^\s*LAW\s+(\d{1,2})\b", re.IGNORECASE)
    starts = {}
    for m in pat.finditer(text):
        starts[int(m.group(1))] = m.start()
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    units = []
    for idx, (n, st) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else len(text)
        units.append(
            {
                "index": n,
                "number": n,
                "category": source.get("title", ""),
                "title": f"Law {n}",
                "slug": f"law-{n:02d}",
                "text": text[st:end].strip(),
            }
        )
    return units
