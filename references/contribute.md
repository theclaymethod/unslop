# Contributing a New AI-ism — internals

The routed step-by-step is in `references/commands/contribute.md` (reachable as a
maintenance path, not a top-level verb). This file is the exhaustive companion:
every command flag, the redaction discipline, the row-diff verification, and the
non-maintainer fork path. Keep it offline until the user has approved both
publication and the final PR body.

## 1. Precheck

```bash
python3 scripts/contribute.py precheck /absolute/path/to/snippet.txt
```

If the snippet is already flagged, the command exits 3 and prints the covering
patterns/categories. Add a REC row instead of a new false-negative row.

## 2. User Confirmation Gate #1

Show the exact snippet to the user and ask whether it may be published in a
public repo. Offer redaction hints from:

```bash
python3 scripts/extract_constraints.py < /absolute/path/to/snippet.txt
```

Redact names, numbers, or private details only with explicit approval. The tell
must remain byte-for-byte intact.

## 3. Scaffold

```bash
python3 scripts/contribute.py scaffold \
  --snippet /absolute/path/to/snippet.txt \
  --tell "exact substring" \
  --category significance_inflation \
  --pattern-name exact-substring-slug \
  --redact "Alice=NAME"
```

The bundle is written under `.unslop/contrib/<slug>/`. Do not commit this
bundle; it is working material for the agent and reviewer.

## 4. Implement the Pattern

Follow `references/maintenance.md` in this order:

1. Copy `.unslop/contrib/<slug>/row_fn.json` into
   `evals/adversarial-evals.json`.
2. Renumber the copied row from the live maxima in
   `evals/adversarial-evals.json`; do not keep the `CONTRIB-FN-*` bundle id in
   the committed suite.
3. Add the literal-use FP row for the category, and add a REC row if an existing
   word is being gated behind collocations.
4. Run the new rows before implementing the pattern and confirm the FN row is
   red while the FP and any REC rows encode the intended boundary.
5. Update the scanner and `references/taboo-phrases.md`.
6. Re-run `python3 scripts/contribute.py verify --bundle .unslop/contrib/<slug>`.
7. Diff the committed eval row against `.unslop/contrib/<slug>/row_fn.json` and
   confirm only expected suite fields changed, such as id, category grouping, or
   row ordering. The specimen stdin and assertion intent must still match.

## 5. Verify

```bash
python3 scripts/contribute.py verify --bundle .unslop/contrib/<slug>
```

Verify refuses reports with TODO markers, checks specimen fidelity, captures the
red-to-green transition for the FN row, and records offline gate tails.

## 6. Run the Full Gate Battery

```bash
python3 evals/run_adversarial.py
python3 evals/build_shared_benchmark.py
python3 evals/build_shared_benchmark.py --check
python3 evals/check_taboo_parity.py
python3 evals/check_pattern_coverage.py
python3 evals/kata_add_pattern.py --run
skill-benchmark validate evals/shared-benchmark.json --strict-leakage
```

If `SKILL.md`, `presets/`, or `references/` changed, also run:

```bash
evals/run_behavioral.sh tune
```

## 7. Render the Report

```bash
python3 scripts/contribute.py report --bundle .unslop/contrib/<slug> > /tmp/pr-body.md
```

## 8. User Confirmation Gate #2

Show the final PR body to the user. Only after the user approves publication:

```bash
git switch -c add-<slug>
git add evals/adversarial-evals.json scripts/banned_phrase_scan.py references/taboo-phrases.md
git commit -m "Add <slug> AI-ism pattern"
gh pr create --title "Add <category> pattern: <tell>" --body-file /tmp/pr-body.md
```

For non-maintainers:

```bash
gh repo fork --remote
git push --set-upstream <fork-remote> add-<slug>
gh pr create --repo <upstream-owner>/unslop --head <fork-owner>:add-<slug> --body-file /tmp/pr-body.md
```

The `gh` commands are for the host agent after approval. Scripts and evals must
never call `gh` or any network command.
