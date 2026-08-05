# Maintenance Procedures

Every change here is eval-first: the example lands in
`evals/fixtures/contracts/scanner-examples.json` and fails before any scanner or
catalog edit makes it pass. Run `python3 evals/check.py --full` for the full
repository check.

## Add a banned phrase (`--add-phrase`)

1. Add a false-negative example (the phrase flags) and a false-positive
   example (a literal or domain use stays clean) to the scanner contract table.
   Run `python3 evals/check_scanner_contract.py` and confirm it fails.
2. Add the phrase to `scripts/banned_phrase_scan.py` `BANNED_PHRASES` with
   category, severity, and suggestion. If the word has a literal sense, gate it
   behind collocations in `STRUCTURAL_PATTERNS` instead, and add a REC recall
   example proving the jargon use still flags.
3. Document it in `references/taboo-phrases.md` (parity is enforced by
   `python3 evals/check_taboo_parity.py`).
4. Run `python3 evals/check.py --full`; expect green with no new xfail.

## Add a structural pattern (`--add-structure`)

Same procedure, but the entry goes in `STRUCTURAL_PATTERNS` with a regex, and
the false-positive example must cover the nearest legitimate construction the regex
could clip.

## Prefer a pair

When a pattern has literal senses or only becomes visible in context, add a
minimal pair under `evals/fixtures/pairs/` instead of relying only on one-line
stdin rows. The `_with` twin should contain one controlled tell, the `_without`
twin should preserve the facts while scanning clean, and the manifest should
name the target category or structure metric. Run `python3 evals/check_pairs.py`
before changing the scanner.

## Coverage gate and category protection (enforced)

`python3 evals/check_pattern_coverage.py` makes the two examples above mandatory, not
conventional:

- **Coverage.** Every `STRUCTURAL_PATTERNS` regex must match at least one contract
  example's corpus, and every `BANNED_PHRASES`
  key must appear in at least one corpus text. A new scanner entry with no eval
  example fails this gate (DOC-09) while every other gate is green. There is no
  grandfather list: an uncovered pattern is a hard failure. If a batch of legacy
  keys is uncovered, add `REC`-style coverage packs (8-12 phrases per stdin, one
  natural sentence each) rather than exempting them.
- **Protection.** Every violation category the scanner can emit must be claimed by
  a `scanner_false_positive` example carrying `"protects": "<category>"`. Backfill the
  field on that category's FP example; add a new FP example
  (asserting `total_violations == 0` on tempting-but-clean prose) for any category
  with no protector. The runner ignores the `protects` key, so it is safe on any
  FP example.

## Rehearse the procedure (the kata)

`python3 evals/kata_add_pattern.py --run` is a meta-eval (DOC-10): in a temp copy
of the repo it adds a throwaway pattern and asserts each safety net fires in order
— coverage catches the example-less entry, parity catches the missing catalog line,
the contract goes green once both exist, and the example goes red if the scanner entry
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

For the full agent-runnable refresh procedure, including the staleness
reporter and the parity-bench cadence, see `references/refresh.md`.
