# Plan 010: DX polish — real --help on three scripts, and a lint baseline that matches the noqa markers

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/check_suggestions.py scripts/readability_metrics.py scripts/extract_constraints.py .github/workflows/evals.yml`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

Two small trust-and-friction fixes. (1) Three scripts the README tells users
to run standalone handle `--help` by treating it as a filename:
`check_suggestions.py --help` prints `Missing file: --help`;
`readability_metrics.py` and `extract_constraints.py` emit a JSON error —
while every sibling script renders proper argparse help. (2) The codebase
carries 36 `# noqa: E402/BLE001` markers — annotations for a ruff/flake8
gate that doesn't exist anywhere (no config file, no CI step), a false
signal that lint is enforced. Add the minimal ruff baseline the markers
already assume.

## Current state

- `scripts/readability_metrics.py:260-262` and
  `scripts/extract_constraints.py:162-164` — raw `sys.argv[1]` handling
  (`if len(sys.argv) > 1: open(sys.argv[1])`), no argparse.
- `scripts/check_suggestions.py:213` — `main(sys.argv[1:])` with manual arg
  handling that treats the first arg as a path.
- Argparse exemplar to copy: `scripts/structure_scan.py`'s parser
  construction (path optional, stdin fallback, `--genre` flag) — read its
  `main()` head and mirror the minimal shape (positional optional path;
  keep EVERY existing flag and behavior byte-compatible; only `-h/--help`
  behavior may change).
- Eval rows invoke these scripts: `grep -c "check_suggestions\|readability_metrics\|extract_constraints" evals/adversarial-evals.json` — nonzero;
  their argv shapes must keep working identically.
- noqa census: `grep -rn "# noqa" scripts/ evals/ | wc -l` → 36 at 217c218;
  codes in use: `E402`, `BLE001`.
- CI: `.github/workflows/evals.yml` — steps listed in plan 001's excerpt;
  a lint step slots after py_compile. ruff is a dev-only tool (pipx/pip in
  CI); the runtime stdlib-only rule is not violated.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| Help works | `python3 scripts/check_suggestions.py --help` | usage text, exit 0 |
| Lint | `ruff check .` (after config) | exit 0 |
| Ruff available | `pipx install ruff` or `pip install --user ruff` | installed (dev tool only) |

## Scope

**In scope**: the three scripts' argument-entry blocks; new `ruff.toml`;
one CI step in `.github/workflows/evals.yml`.

**Out of scope**: fixing lint findings beyond configuration — the baseline
must be chosen so `ruff check .` passes TODAY (rule selection + per-file
ignores), not by editing source. Zero source-logic changes. No formatter
(`ruff format`) adoption — out of scope entirely.

## Git workflow

- Branch: `advisor/010-dx-polish`; two commits (help; lint) or one.

## Steps

### Step 1: argparse for the three scripts

Give each a minimal parser: optional positional `path` (default stdin), plus
any flags the script already parses manually (read each script's arg handling
FIRST and enumerate its accepted argv shapes; `check_suggestions.py` takes a
path per current rows — confirm from an eval row's `command`). Description
line = the script's docstring first sentence.

**Verify**:
- `python3 scripts/<each> --help` → usage, exit 0
- `python3 evals/run_adversarial.py` → green (rows exercise the old shapes)
- `printf 'test' | python3 scripts/readability_metrics.py` → same output as before change (snapshot first)

### Step 2: ruff baseline

Create `ruff.toml` at repo root: select `E`, `F`, `BLE`; set
`line-length` high enough not to fire (or disable `E501`); add per-file
ignores as needed so the CURRENT tree passes with its existing inline noqa
markers meaningful (do not delete any noqa). Iterate: run `ruff check .`,
move whole-category noise into config ignores, keep real signal categories
on. If a rule fires on real code (not style noise), note it in the commit
message rather than fixing code in this plan.

**Verify**: `ruff check .` → exit 0, "All checks passed" (or zero findings).

### Step 3: CI step

Add after py_compile:
```yaml
      - name: Lint (ruff baseline)
        run: pipx install ruff && ruff check .
```

**Verify**: step script runs locally → exit 0.

## Test plan

No new rows (CLI help isn't eval-pinned; the suite re-proves the argv shapes
didn't drift). The before/after stdout snapshot on each script is mandatory.

## Done criteria

- [ ] All three scripts: `--help` → usage text, exit 0
- [ ] Full suite green
- [ ] `ruff check .` exit 0 with committed `ruff.toml`
- [ ] CI has the lint step
- [ ] Zero diffs outside the three entry blocks + ruff.toml + evals.yml
- [ ] `plans/README.md` updated

## STOP conditions

- An eval row invokes one of the three scripts with an argv shape argparse
  can't reproduce compatibly (e.g. flag-like filenames) — report the row id.
- `ruff check .` cannot reach zero without disabling E or F entirely —
  report the finding counts per rule instead of gutting the baseline.

## Maintenance notes

- The ruff baseline is deliberately minimal; tightening (isort rules, etc.)
  is a maintainer taste decision later.
- Reviewer: diff should show argument-parsing blocks and config only.
