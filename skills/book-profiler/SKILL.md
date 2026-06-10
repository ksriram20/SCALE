---
name: book-profiler
description: Read a book's front matter / table of contents and produce a segmentation profile — its concept units (usually chapters), grouped into parts if any — so the engine can split and index it. Use when adding a new book to the library.
---

# Book Profiler

You are given a book's title, author, and its front-matter / table-of-contents
text. Produce a profile that lets the engine split the book into concept units and
locate them in the body.

## Rules

- A **unit** is one self-contained concept — almost always a **chapter**. Pick the
  `unit_label` that fits ("chapter", "principle", "law", "idea", "rule"…).
- List units in **reading order**, with titles **exactly as printed** in the TOC
  (verbatim — they must be findable as headings in the body; do not paraphrase or
  add numbers the title itself doesn't have).
- Group units into the book's **Parts/Sections** if it has them; otherwise use a
  single category named after the book.
- Include only real **content** units. Skip foreword, preface, acknowledgments,
  introduction-if-not-a-chapter, notes, index, "about the author".
- Do **not** invent units. Use only what the TOC actually lists.

## Output — strict JSON only, nothing around it

```
{
  "unit_label": "chapter",
  "unit_label_plural": "chapters",
  "categories": [
    {"name": "<Part name, or the book title if no parts>",
     "units": ["<exact unit title>", "<exact unit title>"]}
  ]
}
```
