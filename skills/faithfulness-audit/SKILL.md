---
name: faithfulness-audit
description: Audit a generated concept + application for two failures — concept drift from the source, and application drift into generic advice — and return a strict JSON verdict. The quality gate before audio.
---

# Faithfulness Audit

The last check before an episode is spoken. Judge two failures separately.

## 1. concept_faithful — held to the SOURCE text
Does the mechanism/explanation match what the author actually wrote? Fail it if it
invents claims, names, or dates not in the source, softens the author's real (often
unsentimental) point into self-help, or conflates it with a different idea.

## 2. application_grounded — held to the MECHANISM, not the source
The application is new reasoning, so judge it against the concept's *mechanism*, not
the source. **Governing test: if the same advice would work without this concept, it
is not grounded** (generic "be confident / communicate clearly / work hard" → fail).
A vivid *invented scenario* is fine; *invented facts about the person* are not.
Quick check: remove the concept — does the advice still stand on its own? Then fail it.

## Bias
A false pass is worse than a false flag. When unsure whether the tactic truly depends
on the mechanism, fail it — regeneration is cheap, a hollow episode is not.

## Output — strict JSON only, nothing around it

```
{ "concept_faithful": true|false, "application_grounded": true|false, "issues": ["<short, specific>"] }
```

Each issue must be concrete enough to guide a rewrite. `issues` is empty only when both pass.
