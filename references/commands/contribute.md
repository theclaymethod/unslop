# /unslop contribute

Turn one AI-ism caught in the wild into a scanner contract example and a structured PR. Route
here on "contribute a pattern", "add this tell", or "I found a new AI-ism".
Everything stays offline until the user approves both publication and the final
PR body. Read `references/contribute.md` for the precheck exit codes, redaction
discipline, row-diff verification, and the non-maintainer fork path.

## Flow

1. **Precheck.** `python3 scripts/contribute.py precheck /abs/path/snippet.txt`.
   Stop if it exits 3. The tell is already covered, so add a REC row rather
   than opening a fresh false-negative row.

2. **User confirmation gate #1 — publication.** Show the exact snippet and ask
   whether it may go in a public repo. Offer redaction hints from
   `python3 scripts/extract_constraints.py < snippet.txt`. Redact only with
   explicit approval, and keep the tell byte-for-byte intact.

3. **Scaffold** the working bundle under `.unslop/contrib/<slug>/` (do not
   commit it):
   ```bash
   python3 scripts/contribute.py scaffold --snippet /abs/path/snippet.txt \
     --tell "exact substring" --category significance_inflation \
     --pattern-name exact-substring-slug --redact "Alice=NAME"
   ```

4. **Implement eval-first**, following `references/maintenance.md`: copy
   `row_fn.json` into `evals/fixtures/contracts/scanner-examples.json`, renumber from the live
   maxima, then set `exact_total` to the new `examples` length. Add the
   literal-use FP example (and a REC example if a word is gated
   behind a collocation). Confirm the FN example is **red** before you touch the
   scanner, then update `scripts/banned_phrase_scan.py` and
   `references/taboo-phrases.md` until it goes **green** while the FP example holds.

5. **Verify:** `python3 scripts/contribute.py verify --bundle .unslop/contrib/<slug>`.
   It refuses TODO markers, checks specimen fidelity, and captures the
   red-to-green transition.

6. **Full deterministic gate battery:** `python3 evals/check.py --full`.

7. **Render the PR body:**
   `python3 scripts/contribute.py report --bundle .unslop/contrib/<slug> > pr-body.md`.

8. **User confirmation gate #2 — publication of the PR.** Show the final PR
   body, get approval, then branch, `git add` the three changed files, commit,
   and use `gh pr create` (or the non-maintainer fork path in
   `references/contribute.md`). Network access belongs to the host agent.

The resulting branch contains the contract example, scanner change, and taboo-catalog
entry.
