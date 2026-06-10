---
name: concept-extraction
description: Extract a single concept/unit from a source book grounded ONLY in the provided text, with verbatim citations and the author's true mechanism — never folk-wisdom drift. Use when turning a raw section into the factual backbone the rest of the pipeline trusts.
---

# Concept Extraction

You extract the TRUE content of one concept from a source work, grounded ONLY in
the source text provided to you. The specific book, author, and the unit you are
working on are named in the input. Your output is the factual, cited backbone every
later step trusts. If you drift here, the whole episode inherits the lie — this is
what separates this product from AI-slop "wisdom" channels that misattribute and
invent.

## Hard rules

1. **Ground every claim in the supplied source text.** If it is not in the excerpt
   in front of you, it does not go in your output. You are not recalling the book
   from memory; you are reading *this passage*.
2. **Name the real mechanism, not the comfortable one.** Serious authors are
   specific and often unsentimental. Capture the sharp, actual engine of the idea
   — the precise thing that makes it work — not a softened paraphrase.
3. **Quote verbatim.** Pull 1–3 short exact phrases from the source. If you cannot
   find a supporting phrase for a claim, the claim is suspect — cut it.
4. **No self-help smoothing.** Do not sand the author's real, precise point into
   generic motivation.
5. **No invented history, names, or anecdotes.** If a story is not in the excerpt,
   do not summon it from memory.

## Output — strict JSON only, nothing around it

```
{
  "title": "<the concept's name, exactly as the author titles it>",
  "mechanism": "<1-2 sentences: the precise engine, the WHY it works>",
  "explanation": "<~N words, faithful, plain, grounded in the source>",
  "quotes": ["<short verbatim phrase from source>", "..."]
}
```

## Self-check before you answer

- Could a reader who never read the book be **misled** about what the author argued? Fix it.
- Is every quote **actually present, verbatim**, in the source? If unsure, drop it.
- Did I **soften** the author's real point? Restore its edge.
- Did I add a fact, name, or date the excerpt does not contain? Remove it.
