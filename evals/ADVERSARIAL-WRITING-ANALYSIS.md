# Adversarial Analysis: unslop's Writing Quality

A red-team audit of the *writing the skill produces*, not just its detection. An
incentivized adversary was tasked to prove a single thesis and to attack faithful
skill outputs (generated first, so the critique isn't a strawman). Every claim
below was reproduced by hand before acting on it.

## Thesis tested

> "unslop does not make text sound human. It trades one detectable register
> (corporate AI slop) for a different, equally-detectable register — clipped
> fragments, fake punchiness, 'Not X. Y.' contrasts, manufactured folksiness —
> while quietly deleting nuance, hedges, and information. And it passes its own
> scanner precisely because the scanner doesn't know its own house style is a tell."

**Verdict: supported (high confidence).** The skill's own gold examples and two of
four presets prove the register swap, and the scanner scored those gold outputs at
**0 violations**. The validation pipeline cannot see the semantic facts (negations,
scope, conditionals) its own `fact-preservation.md` calls must-preserve. This was
the most important finding of the project: a "clean" verdict was partly an artifact
of the detector being blind to the skill's house style and to meaning.

## Findings, evidence, and what changed

| ID | Severity | Finding (verified) | Status |
|----|----------|--------------------|--------|
| **B1** | blocker | Scanner blind to its own house style. Gold `"Building products is hard. Not the technology. The people."` → **0**; clause form `"The problem isn't meetings. It's unclear agendas."` → **1**. Staccato triplet `"Move fast. Handle uncertainty. Use what you're good at."` → **0**. | **Fixed.** New `anti_slop_register` scanner patterns (fragment contrast + staccato run, soft) now flag both; AS-01/02 + FP-12 guard it. |
| **B2** | blocker | Validation is theater for semantic facts. `extract_constraints` on `"X does not support Y. Most users (73%) prefer it. If A, then B. See Section 12(b)."` returned only `73%` (+ junk). A rewrite dropping the negation and `Section 12(b)` reported `passed: true`. | **Fixed/mitigated.** References now extracted + hard-validated (PRES-08/09); negation/scope/conditional drops emit `warnings` (SEM-01); SKILL.md no longer claims validation covers meaning. |
| **B3** | blocker | De-hedging destroys text where the hedge *is* the content (medical/legal/scientific). "preliminary / observational / not causal / confounders" deleted; output reads as casual overclaim. | **Mitigated.** SKILL.md "Register & genre guards" forbids de-hedging regulated/technical content; behavioral evals SKILL-HEDGE-03, SKILL-LEGAL-02 guard it. Genuinely hard to enforce mechanically. |
| **B4** | major | Em-dash "default to zero" contradicted by 2/4 presets' gold examples, and obeying it manufactures comma splices. | **Fixed.** SKILL.md rule rewritten: sparing appositive dash allowed, never trade a dash for a splice. SKILL-EMDASH-01 guards. |
| **B5** | major | "When in doubt, cut" + crisp 20-word cap delete causal caveats / scope ("in most cases", "can", named evidence). `diff_check` flags 60% over-edit but it's advisory and the 0-violation scan overrides it. | **Mitigated.** Scope-word drops now warn (B2 machinery); SKILL-OVEREDIT-01 + SKILL-STACCATO-01 guard. Making the over-edit gate hard is left as a follow-up. |
| **B6** | major | personality-guide models first-person quirk ("I don't put on pants until noon"); applied to impersonal copy this *invents content* and is its own tell. | **Mitigated.** SKILL.md guard: don't fabricate first-person experience. SKILL-NOINVENT-01 guards. |
| **B7** | minor | Readability rhythm flags gated behind `sentence_count > 3`, so short staccato outputs passed clean. | **Fixed.** New staccato flag (longest run of ≤5-word sentences ≥ 3, or avg < 6) with no count gate. AS-03 guards. |
| **B8** | minor | Warm-email rewrite strips warmth into curtness ("No rush if not."); the warm preset conflates AI enthusiasm with human warmth. | **Mitigated.** SKILL.md "match register, don't flatten it"; SKILL-WARMTH-01 guards. |

## New-register tell phrases the scanner could not see (now: can)

All scored **0 violations** before this round; the `anti_slop_register` patterns
now catch the first two families. The rest are punch-endings/aphorisms that remain
hard to detect without false positives and are addressed via the SKILL guards and
behavioral evals rather than the regex:

- `Not the technology. The people.` — bare fragment contrast *(now flagged)*
- `Move fast. Handle uncertainty. Use what you're good at.` — staccato triplet *(now flagged)*
- `The rest guess.` / `Adapt or fall behind.` — two/three-word punch closers
- `Good teams fail fast. Bad teams avoid failure.` — symmetric antithesis
- `Open offices are where focus goes to die.` — manufactured edgy aphorism
- `I don't put on pants until noon and accomplish nothing.` — forced folksy quirk

**The structural signature** the scanner was blind to: sentence fragments,
sub-five-word sentences, and antithesis without a connective. That *is* the
"anti-slop" voice — and the skill's own edit-library and personality-guide teach it.

## What's fixable vs. unfixable by design

- **Fixable (done):** B1, B7 (detectors), B2 references + warnings, B4 em-dash rule.
- **Mitigated, not solved:** B3, B5, B6, B8 are register/judgment problems a regex
  can't enforce. The defense is (a) explicit SKILL guards and (b) behavioral evals
  that a human/LLM judge checks. A faithful operator can now follow the guards; the
  defaults no longer push them off a cliff.
- **By design / open:** the deepest tension is that the skill's *aesthetic ideal*
  (punchy, compressed, fragment-friendly) is itself a detectable register. Truly
  fixing it means revising the gold examples in `edit-library.md` and
  `personality-guide.md` toward genuine sentence-length variety — a content change
  to the skill's taste, not just its tooling. Flagged for follow-up.

## Method note

A neutral executor produced faithful skill rewrites of six diverse inputs (LinkedIn
slop, a nuance-heavy technical paragraph, a personal narrative, a sensitive email,
already-decent prose, a compression-prone argument); the adversary independently
generated its own faithful outputs and attacked them, ran them back through the
scanner, and built worst-case inputs (medical, legal, dialogue). The strongest
claims (B1, B2, B7) were re-verified directly in this repo before any change.
