<!--
Built the row-first, per CONTRIBUTING.md and references/contribute.md?
scripts/contribute.py report renders most of this for you.
-->

## Specimen & source

Quote the exact specimen and where it was seen (model, site, or input).

## Red-first proof

Paste the FN row's output before the scanner or catalog change (the row
must be red here).

## Coverage

| row id | kind | what it pins |
|---|---|---|
| | FN | |
| | FP | |
| | REC | |

## Gate results

Paste the `run_adversarial.py` tail and the `check_pattern_coverage.py`
result.

## Confirmation

- [ ] Specimen publication was approved by the source; redactions (if any)
      keep the tell byte-for-byte intact.
- [ ] The FN row was verified red before the fix.
- [ ] No case was marked `xfail` to grandfather a gap; `FP-06` remains the
      only documented XFAIL.
