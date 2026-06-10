SOURCE WORK: "{book_title}" by {book_author}
UNIT: this is one {unit_label} titled "{unit_title}" (group: {category}).

SOURCE TEXT FOR THIS {unit_label_upper}:
"""
{source}
"""

Extract this {unit_label}. Use "{unit_title}" as the title. Target roughly
{concept_words} words for the explanation. Return only the JSON object described
in your instructions — no commentary, no code fences.
