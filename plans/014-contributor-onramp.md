# Plan 014: Give the contribute flywheel a human on-ramp

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- references/contribute.md references/commands/contribute.md CLAUDE.md AGENTS.md .github/`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: direction / docs
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

The product's growth model depends on outside contributors turning
wild-caught AI-isms into eval rows and PRs — the pipeline is fully built
(`scripts/contribute.py`, `references/contribute.md`,
`references/commands/contribute.md`, fork path documented). But the repo has
no `CONTRIBUTING.md`, no issue templates, and no PR template; `.github/`
contains only the CI workflow. A stranger landing on GitHub sees an
agent-oriented internal flow with no human front door. Thin landing docs that
link into the existing flow complete the flywheel without duplicating
doctrine (drift risk is real — everything here must LINK, not restate).

## Current state

- `.github/` contains only `workflows/evals.yml` (verified 217c218).
- No `CONTRIBUTING.md` at root (verified).
- The content to link to (read all four before writing a word):
  - `references/contribute.md` — full flow incl. the two user-confirmation
    gates and the non-maintainer fork path (~lines 104-116: host agent runs
    `gh` only after approval; scripts never call the network).
  - `references/commands/contribute.md` — the agent command flow.
  - `CLAUDE.md` "Add a New Pattern" — the eval-first recipe (red row first,
    FN/FP/REC coverage, no grandfathering).
  - `docs/PRODUCT.md` — bounds (what the tool refuses to become).
- GitHub convention: issue forms live in `.github/ISSUE_TEMPLATE/*.yml`
  with a `config.yml`; PR template at `.github/PULL_REQUEST_TEMPLATE.md`.
- Doc hygiene rule: every new prose file must pass
  `python3 scripts/banned_phrase_scan.py <file>` (0 hard) — these docs
  advertise a slop-removal tool; hold them to 0 soft as well.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Scanner | `python3 scripts/banned_phrase_scan.py <each new file>` | `"total_violations": 0` |
| Structure | `python3 scripts/structure_scan.py --genre docs <each>` | no flags |
| Suite | `python3 evals/run_adversarial.py` | green (docs are outside gate scope, but confirm) |

## Scope

**In scope** (all new files + two one-line edits):
- `CONTRIBUTING.md`
- `.github/ISSUE_TEMPLATE/new-ai-ism.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `README.md` — one line in its contribution section pointing at CONTRIBUTING.md (find the existing growth/contribute section first)

**Out of scope**: any edit to the linked reference docs; restating the
add-a-pattern recipe (link it); CODE_OF_CONDUCT and governance files
(maintainer's call, not this plan).

## Steps

### Step 1: CONTRIBUTING.md (~60 lines max)

Sections: What contributions look like here (a new AI-ism = a specimen +
red-first eval row — link CLAUDE.md's recipe); The fast path (run the
`/unslop contribute` agent flow — link `references/commands/contribute.md`);
The manual path (link `references/contribute.md`); Ground rules (eval-first,
no grandfathering, scanners must pass on prose, verification commands);
Where to ask (issues). Every section links rather than restates; the file
contains ZERO duplicated procedure steps.

**Verify**: both scanners clean; every relative link resolves
(`python3 - <<'EOF'` … parse markdown links, assert each target exists).

### Step 2: Issue form

`new-ai-ism.yml`: fields — the exact specimen (textarea, required), where it
was seen (model/site, input), why it reads as AI (textarea), redaction
confirmation (checkbox: "I've removed private info from the specimen" —
mirror the redaction rule in `references/contribute.md`). Plus `config.yml`
with `blank_issues_enabled: true` and a contact link to CONTRIBUTING.md.

**Verify**: YAML parses (`python3 -c "import yaml"` if available, else
`python3 -c "import json"`-adjacent check is insufficient — use
`ruby -ryaml` alternative or just careful review + GitHub's schema is
forgiving; at minimum `python3 -c "print(open('.github/ISSUE_TEMPLATE/new-ai-ism.yml').read())"` and inspect); scanner clean on the prose strings.

### Step 3: PR template

Mirror `contribute report`'s structure (read a generated report via
`references/contribute.md`'s description): Specimen & source / Red-first
proof (paste the failing row output before the fix) / Coverage (FN + FP +
REC row ids) / Gate results (`run_adversarial.py` tail + coverage gate) /
Confirmation checkboxes (specimen redacted; rows red-first; no grandfathered
xfail). Keep under 40 lines.

**Verify**: scanner clean.

### Step 4: README pointer

One sentence in the README's contribution/growth section linking
CONTRIBUTING.md.

**Verify**: `python3 scripts/banned_phrase_scan.py README.md` → 0; suite green.

## Test plan

Link-resolution check (step 1) + scanner hygiene on every file. No eval rows
(GitHub meta-files are outside the suite's jurisdiction — deliberately).

## Done criteria

- [ ] Four new files exist; README pointer added
- [ ] All prose scanner-clean (0 hard, 0 soft) and structure-clean
- [ ] All relative links resolve
- [ ] Suite green; `git status` clean outside scope
- [ ] `plans/README.md` updated

## STOP conditions

- `references/contribute.md`'s confirmation gates differ from what this plan
  summarizes — the template must mirror the doc; report the discrepancy
  rather than paraphrasing.
- README has no contribution section to anchor the pointer — report where
  you'd put it instead of restructuring the README.

## Maintenance notes

- These files LINK into gate-checked docs; when the contribute flow changes,
  the links hold but the summaries could rot — keep them summary-free
  (that's why the plan bans restating).
- Reviewer: check the issue form's redaction checkbox matches the flow's
  actual redaction rule verbatim.
