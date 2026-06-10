# Audit rubric — concrete pass/fail patterns

## concept_faithful

PASS when:
- Every substantive claim in the explanation maps to something in the source.
- The mechanism matches the author's actual argument, edge intact.

FAIL when:
- The explanation introduces an idea, story, name, or statistic absent from the source.
- The mechanism is the "nice" version (humility, teamwork, positivity) where the
  source is strategic/cynical.
- The law is conflated with a different, adjacent idea.

## application_grounded

PASS when:
- You can point to the exact step in the tactic that *only* works because of this
  mechanism.
- The situation is specific and plausible for the person's domain.

FAIL when:
- The advice is interchangeable with generic career/self-help wisdom.
- The tactic restates the law but never operationalises the mechanism.
- It moralises ("the ethical thing is...") instead of applying the (amoral) law.
- It invents facts about the *person* (not just the situation).

## Quick decision

Ask: "Remove the concept entirely — does this advice still stand on its own?"
- Still stands → `application_grounded: false`.
- Collapses without the mechanism → likely PASS.
