# Decisions

Durable record of tradeoffs the product has already made, so the reasoning
does not live only in a commit message someone has to go dig up. Each entry
is dated to when the decision was made (not when it was copied here), and
cites the doc or commit that carries it. New decisions get a new entry at
decision time; nothing here is retroactively rewritten.

## 2026-07-06 — Agent-invoked only, no daemons or hooks

**Decision:** Linting and refresh run when a host agent invokes them.
Nothing in this repo runs as a cron job, a pre-commit hook, or an editor
extension.

**Why:** The host agent is the runtime. A background scheduler would be a
second execution path with its own failure modes, and the repo ships as
plain scripts specifically so any host agent can run them directly.

**Revisit-when:** An operator needs scheduled refresh outside an agent
session. `scripts/refresh_status.py` is built as the reporter half of that
path on purpose (see `references/refresh.md`), so a future scheduler only
has to call it, not invent staleness detection.

**Source:** `docs/PRODUCT.md` (Identity and shape).

## 2026-07-06 — English-only, with a graceful decline

**Decision:** Non-English input gets a cheap detection and a clear decline
rather than an attempt at cross-language scanning.

**Why:** The scanner catalog is built from English-language AI-writing
tells; running it against other languages would produce noise, not signal.

**Revisit-when:** Demand for another language's AI-isms catalog appears and
someone proposes a scanner strategy for it.

**Source:** `docs/PRODUCT.md` (Bounds).

## 2026-07-06 — No packaging

**Decision:** The repo is the artifact. There is no published package, and
none is planned unless distribution genuinely requires it.

**Why:** Entry points are plain scripts under `scripts/`, runnable by any
host agent without an install step.

**Revisit-when:** A hosting environment appears that cannot run the scripts
directly and needs a packaged distribution to reach them.

**Source:** `docs/PRODUCT.md` (Identity and shape).

## 2026-07-06 — No rights or attestation checks on mimicry samples

**Decision:** Mimicry accepts any writing style the user supplies samples
for. There is no rights-verification or attestation machinery; the sheet of
samples is the only credential.

**Why:** The product treats consent to publish as the user's problem to
manage, not one the tool can verify from the sample text itself.

**Revisit-when:** Mimicry usage grows past individual or team use in a way
that makes provenance disputes likely.

**Source:** `docs/PRODUCT.md` (Bounds).

## 2026-07-06 — Removal-dominant balance on the product axis

**Decision:** Product weight sits roughly 70/30 toward removal (detect and
strip AI-writing patterns) over reconstruction (write in a specific human's
voice).

**Why:** Removal is deterministic, cheap, and objectively benchmarkable —
the trust asset the rest of the product stands on. Reconstruction is
generative and register-sensitive, and it only ships under removal's gates.

**Revisit-when:** Measured mimic/rewrite usage or quality data shifts the
axis's practical value away from removal.

**Source:** `docs/PRODUCT.md` (The axis).

## 2026-07-06 — WP8 pair fixtures: word floors and length balance queued, not enforced

**Decision:** The minimal-pair fixtures under `evals/fixtures/pairs/` shipped
without raising every fixture to the review's spec word floors, without a
corpus-level length-balance check, and without the `vague_attribution` pair's
single-difference rework. `check_pairs.py` does not yet enforce these.

**Why:** The reviewed fixtures already passed pair-hygiene checks (existence,
word-delta, clean-without, with-target); the remaining polish was accepted as
a queued follow-up rather than a blocker for landing the pair infrastructure.

**Revisit-when:** A new pair addition re-exposes the with-twin length skew
(+2.4 words at commit time), or `check_pairs.py` gains fixture-floor
enforcement.

**Source:** commit `05f2363`.

## 2026-07-06 — Voice impostor pool and background calibration queued

**Decision:** The deterministic voice scorer shipped with a synthetic
impostor pool and no real `--background` calibration for delta z-scores,
rather than a same-genre impostor pool and measured background calibration.

**Why:** The shipped scorer already passed its adversarial checks (mechanical
attacks lose by 0.85+ composite, separation diagonal wins at five seeds); the
follow-ups were approved-with-fixes and queued rather than blocking.

**Revisit-when:** `voice_score.py`'s impostor pool or `--background`
calibration path is reworked, or a same-genre impostor scenario produces a
measurable gap the synthetic pool misses.

**Source:** commit `41b60d1`.

## 2026-07-06 — Per-category protects-grain redesign deferred

**Decision:** `check_pattern_coverage.py`'s per-category `protects` field
keeps its current grain (one FP row can claim an entire category) rather
than a finer-grained redesign.

**Why:** Explicitly deferred as out of scope for a contract-safe
consolidation pass — the existing grain still made every category
claimable, and a redesign risked changing pinned CLI/JSON behavior in the
same change.

**Revisit-when:** A future refactor specifically touches
`check_pattern_coverage.py`'s `protects` handling.

**Source:** commit `d6f6321`.

## 2026-07-06 — `run_mimic_refine.py`'s `build_report()` left as one function

**Decision:** `build_report()` in `evals/run_mimic_refine.py` was not
decomposed during the internals-consolidation pass that touched most of its
neighbors.

**Why:** Explicitly deferred as out of scope for the same contract-safe
pass as the protects-grain redesign above — decomposing it risked behavior
drift in a change meant to be a pure refactor.

**Revisit-when:** `build_report()` needs new report fields, or a bug traces
back into it.

**Source:** commit `d6f6321`.

## 2026-07-04 — FP-06 (literal "delve into a place") is the one intentional XFAIL

**Decision:** `evals/run_adversarial.py` pins exactly one expected XFAIL,
`FP-06`: the scanner still flags the literal sense of "delve into a place"
even though only the figurative "delve into a topic" is the intended AI-ism.

**Why:** Distinguishing the literal and figurative senses is beyond a
pattern scanner, and dropping the `delve into` pattern to fix the false
positive would cost more recall on the real AI-ism than the rare false
positive is worth.

**Revisit-when:** The scanner gains sense disambiguation beyond pattern
matching, or a cheap-enough contextual rule is found that separates the two
senses without dropping recall.

**Source:** `evals/CRITIQUE.md` (Status section); `EXPECTED_XFAIL` pinned in
commit `efd7e0e`.
