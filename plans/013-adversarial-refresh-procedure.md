# Plan 013: Make the adversarial-refresh promise operational (procedure + staleness signal + decision record)

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- docs/ references/maintenance.md scripts/wiki_sync.py evals/`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/007 (wiki_sync seam makes the staleness check testable) — soft
- **Category**: direction
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`docs/PRODUCT.md`'s Growth section promises: "Growth comes from adversarial
refresh: live bench outputs supply fresh specimens, contribute turns each
specimen into a red-first row … and nothing relies on anyone's good habits."
Today, everything relies on someone's good habits: refresh means a maintainer
remembering to run `wiki_sync check`, re-run the model-parity bench, and
funnel misses through contribute. The decided constraint — agent-invoked, no
daemons/hooks — rules out cron; what's missing is (a) a written, agent-
runnable refresh procedure, (b) a deterministic staleness signal an agent or
CI can surface, and (c) — a meta-finding from this audit — a durable home
for decided tradeoffs, several of which currently live only in commit
messages where a fresh auditor provably could not find them.

## Current state

- `docs/PRODUCT.md:98-102` — the Growth promise (quoted above).
- `references/maintenance.md` — maintenance doc; `:73-87` covers
  `wiki_sync check/diff` usage; no cadence, no staleness concept.
- `scripts/.wiki_sync_state.json` — the only refresh state in the repo
  (last-synced revision; read `wiki_sync.py:357` `cmd_check` for its shape).
- `evals/run_model_parity.py` — the live bench; results recorded manually in
  `references/pipeline.md` ("2026-07-06" tiering table).
- Decided-tradeoff locations today: commit messages (e.g. the WP8 fixture
  word-floor queue, the voice impostor-calibration queue, the per-category
  protects-grain defer), `docs/PRODUCT.md` (product bounds), scattered
  reference docs. No single decisions file; this audit's direction subagent
  searched for the protects-grain defer and could not find it in any doc.
- Doc-gating convention: prose docs are scanner-gated (0 hard) and some are
  parity-gated; new docs should pass `banned_phrase_scan` and
  `structure_scan --genre docs`.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Suite | `python3 evals/run_adversarial.py` | green |
| Staleness (new) | `python3 scripts/refresh_status.py` | JSON: days since wiki sync / parity bench / last new pattern row |
| Scanner hygiene | `python3 scripts/banned_phrase_scan.py <each new/edited doc>` | 0 hard |

## Scope

**In scope**: new `references/refresh.md` (the procedure); new
`scripts/refresh_status.py` (staleness reporter, stdlib-only, network-free);
new `docs/DECISIONS.md` (decision record, seeded from known decisions);
one-line pointers from `references/maintenance.md` and `docs/PRODUCT.md`;
optionally one eval row smoke-testing `refresh_status.py`.

**Out of scope**: any scheduler/daemon/hook (doctrine); automation that
calls models or the network from CI; changing PRODUCT.md's Growth wording
beyond a pointer.

## Steps

### Step 1: `docs/DECISIONS.md`

Create the decisions record: one dated entry per decided tradeoff, each with
Decision / Why / Revisit-when. Seed with the decisions currently findable in
the repo (from `docs/PRODUCT.md`: agent-invoked only, English-only, no
packaging, no rights checks, removal-dominant balance) plus these
commit-message-only decisions — copy their reasoning from `git log` (search
`git log --grep="follow-up" --grep="queue" --grep="defer" -i --oneline` and
read the named commits): the WP8 pair-fixture word-floor/length-balance
queue, the voice impostor same-genre/background calibration queue, the
per-category (not per-pattern) `protects` coverage grain, the refine
`build_report` monolith acceptance, FP-06 as the single intentional xfail.
Every entry cites its source (doc or commit sha).

**Verify**: scanners clean on the doc; every entry has a sha or doc citation.

### Step 2: `references/refresh.md`

Write the agent-runnable procedure (~1 page): (1) run
`python3 scripts/refresh_status.py`; (2) if wiki stale → `wiki_sync check`
/ `diff` → contribute flow for new tells; (3) if bench stale → run the
parity matrix live (pointer to `references/pipeline.md`'s documented
commands + the eval-gating rule); (4) funnel every miss through
`references/commands/contribute.md`; (5) record results (pipeline.md table
+ TUNE-RESULTS conventions). State the cadence expectation as guidance
("stale after 90 days" — match whatever thresholds step 3 encodes).

**Verify**: scanners clean; every referenced command exists (run each
`--help`).

### Step 3: `scripts/refresh_status.py`

Stdlib-only, network-free reporter emitting JSON:
`{"wiki_sync": {"last": <date|null>, "days": N|null, "stale": bool}, "parity_bench": {...}, "newest_pattern_row": {...}}`.
Sources: `.wiki_sync_state.json` mtime/content for wiki; the dated tiering
table in `references/pipeline.md` for the bench (parse the `2026-07-06`-style
date via regex — document the convention it relies on); newest row = git log
date of the last commit touching `evals/adversarial-evals.json` (subprocess
git, argv list, no shell). Thresholds: wiki 90d, bench 180d, rows 60d —
constants at top with a comment saying they're guidance, exit 0 always
(reporter, not gate).

**Verify**: `python3 scripts/refresh_status.py` → valid JSON with the three
keys; runs <2s; no network (works offline).

### Step 4 (optional, if plan 004 landed): one smoke row

Add a row invoking `refresh_status.py`, asserting exit 0 +
`stdout_contains: "wiki_sync"` — keeps the reporter from rotting.

**Verify**: suite green.

## Test plan

The optional smoke row; otherwise verification is per-step. The DECISIONS
file's value is auditability — the "test" is that a future auditor can find
every defer without reading git log (this audit's demonstrated failure mode).

## Done criteria

- [ ] `docs/DECISIONS.md` exists, cited, scanner-clean
- [ ] `references/refresh.md` exists, scanner-clean, all commands real
- [ ] `refresh_status.py` emits valid JSON offline, <2s
- [ ] Pointers added in maintenance.md + PRODUCT.md (one line each, scanner-clean)
- [ ] Suite green
- [ ] `plans/README.md` updated

## STOP conditions

- A commit-message decision can't be found/reconstructed from git log —
  list what you searched; do not invent rationale.
- `pipeline.md`'s bench table has no parseable date convention — report its
  actual format; don't guess-parse.

## Maintenance notes

- New decisions go in DECISIONS.md at decision time — cheap now, impossible
  to reconstruct later (this plan exists because of exactly that).
- If the operator later wants scheduled refresh, the reporter is the
  building block; the scheduler stays out of this repo per doctrine.
