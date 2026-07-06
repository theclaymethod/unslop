# Maintenance Procedures

Every change here is eval-first: the row lands in `evals/adversarial-evals.json`
and fails before any scanner or catalog edit makes it pass. Run
`python3 evals/run_adversarial.py --list-gates` for the full gate matrix.

## Add a banned phrase (`--add-phrase`)

1. Add a `script` false-negative row (the phrase flags) and a false-positive
   row (a literal or domain use stays clean) to `evals/adversarial-evals.json`.
   Run `python3 evals/run_adversarial.py` and confirm the new rows fail.
2. Add the phrase to `scripts/banned_phrase_scan.py` `BANNED_PHRASES` with
   category, severity, and suggestion. If the word has a literal sense, gate it
   behind collocations in `STRUCTURAL_PATTERNS` instead, and add a REC recall
   row proving the jargon use still flags.
3. Document it in `references/taboo-phrases.md` (parity is enforced by
   `python3 evals/check_taboo_parity.py`).
4. Re-run the suite; expect green with no new xfail.

## Add a structural pattern (`--add-structure`)

Same procedure, but the entry goes in `STRUCTURAL_PATTERNS` with a regex, and
the false-positive row must cover the nearest legitimate construction the regex
could clip.

## Coverage gate and category protection (enforced)

`python3 evals/check_pattern_coverage.py` makes the two rows above mandatory, not
conventional:

- **Coverage.** Every `STRUCTURAL_PATTERNS` regex must match at least one script
  row's corpus (its stdin or a referenced fixture), and every `BANNED_PHRASES`
  key must appear in at least one corpus text. A new scanner entry with no eval
  row fails this gate (DOC-09) while every other gate is green. There is no
  grandfather list: an uncovered pattern is a hard failure. If a batch of legacy
  keys is uncovered, add `REC`-style coverage packs (8-12 phrases per stdin, one
  natural sentence each) rather than exempting them.
- **Protection.** Every violation category the scanner can emit must be claimed by
  a `scanner_false_positive` row carrying `"protects": "<category>"`. Backfill the
  field on the FP row whose failure mode names that category; add a new FP row
  (asserting `total_violations == 0` on tempting-but-clean prose) for any category
  with no protector. The runner ignores the `protects` key, so it is safe on any
  FP row.

## Rehearse the procedure (the kata)

`python3 evals/kata_add_pattern.py --run` is a meta-eval (DOC-10): in a temp copy
of the repo it adds a throwaway pattern and asserts each safety net fires in order
— coverage catches the row-less entry, parity catches the missing catalog line,
the runner goes green once both exist, and the row goes red if the scanner entry
is later removed. Run it before touching the maintenance tooling; if a refactor
breaks a safety net, this kata turns red.

## List current patterns

```bash
python3 - <<'PY'
from scripts.banned_phrase_scan import BANNED_PHRASES
for k in sorted(BANNED_PHRASES): print(k)
PY
rg -n '"pattern":' scripts/banned_phrase_scan.py   # structural patterns
```

## Wiki sync (`--wiki-sync`)

Syncs pattern rules with Wikipedia's
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) page.

1. Check for updates: `python3 scripts/wiki_sync.py check` (exit 0 = no updates).
2. Get the structured diff: `python3 scripts/wiki_sync.py diff` (JSON with
   change type, section, words).
3. For each new word or phrase, follow "Add a banned phrase" above — eval rows
   first, then scanner, then catalog.
4. Verify: `python3 scripts/banned_phrase_scan.py < /dev/null` (no syntax
   errors), then the full suite.

Only adopt phrases that are genuine AI tells in general prose. Skip
Wikipedia-specific patterns (broken wikitext, DOI formatting, citation graffiti).
