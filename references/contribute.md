# Contributing a New AI-ism — internals

The routed procedure lives in `references/commands/contribute.md`. This
exhaustive companion covers every command flag, the redaction discipline, the
row-diff verification, and the non-maintainer fork path. Keep it offline until
the user has approved both publication and the final PR body.

## 1. Precheck

```bash
python3 scripts/contribute.py precheck /absolute/path/to/snippet.txt
```

If the snippet is already flagged, the command exits 3 and prints the covering
patterns/categories. Stop there. Add a REC example instead of a new
false-negative example.

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

The bundle is written under `.unslop/contrib/<slug>/`. Do not publish it. It is
working material for the agent and reviewer.

## 4. Implement the Pattern

Follow `references/maintenance.md` in this order:

1. Copy `.unslop/contrib/<slug>/row_fn.json` into
   `evals/fixtures/contracts/scanner-examples.json`.
2. Renumber the copied example from the live maxima in that table; do not keep
   the `CONTRIB-FN-*` bundle id in the committed contract. Set `exact_total` to
   the resulting `examples` array length.
3. Add the literal-use FP example for the category, and add a REC example if an existing
   word is being gated behind collocations.
4. Run the scanner contract before implementation and confirm the FN example is
   red while the FP and any REC examples encode the intended boundary.
5. Update the scanner and `references/taboo-phrases.md`.
6. Re-run `python3 scripts/contribute.py verify --bundle .unslop/contrib/<slug>`.
7. Before treating the example as ready, diff it against
   `.unslop/contrib/<slug>/row_fn.json` and verify that only expected suite
   fields changed, such as the id, category grouping, or row ordering; the
   specimen stdin and assertion intent must still match because redaction or
   implementation work does not authorize a silent change to the reported tell.

## 5. Verify

```bash
python3 scripts/contribute.py verify --bundle .unslop/contrib/<slug>
```

Verify refuses reports with TODO markers, checks specimen fidelity, captures the
red-to-green transition for the FN row, and records offline gate tails.

## 6. Run the Full Gate Battery

```bash
python3 evals/check.py --full
```

## 7. Render the Report

```bash
python3 scripts/contribute.py report --bundle .unslop/contrib/<slug> > /tmp/pr-body.md
```

## 8. User Confirmation Gate #2

Show the final PR body to the user. Only after the user approves publication:

```bash
git switch -c add-<slug>
git add evals/fixtures/contracts/scanner-examples.json scripts/banned_phrase_scan.py references/taboo-phrases.md
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
