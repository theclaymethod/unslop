# Contributing to unslop

Thanks for looking. This repo grows one way: a wild-caught AI-ism turns into a
red-first eval row, then a PR. There is no other contribution shape — no
style-only PRs, no "I think this reads better" rewrites without a row behind
them.

## What contributions look like here

A contribution starts with a specimen: a real sentence or paragraph, caught in
the wild, that reads as machine-written. It becomes an eval row that fails
before the fix and passes after. See [`CLAUDE.md`](CLAUDE.md)'s "Add a New
Pattern" for the exact recipe the suite enforces.

## The fast path

If you're working with an agent that has this skill loaded, say "contribute a
pattern" or "add this tell" and let it run the flow. The routed steps live in
[`references/commands/contribute.md`](references/commands/contribute.md).

## The manual path

Running the pipeline yourself, or want the full detail behind each step
(precheck exit codes, the redaction discipline, the row-diff verification, the
non-maintainer fork path)? Read [`references/contribute.md`](references/contribute.md).

## Ground rules

- **Eval-first.** The row lands red before any scanner or catalog line
  changes.
- **No grandfathering.** `evals/check_pattern_coverage.py` fails the build if
  a pattern ships without its false-positive protection row.
- **Prose passes the scanners it ships.** Anything you write here, this file
  included, has to clear `scripts/banned_phrase_scan.py` and
  `scripts/structure_scan.py --genre docs` clean.
- **Green before you ask for review.** Run the commands under
  [`CLAUDE.md`](CLAUDE.md)'s "Required Checks" and paste the tails into your
  PR.

## Where to ask

Open an issue with the specimen and where you saw it. Use the
[New AI-ism](.github/ISSUE_TEMPLATE/new-ai-ism.yml) issue form if you have a
candidate tell but haven't built the row yet; open a PR directly if you've
already run the pipeline above.
