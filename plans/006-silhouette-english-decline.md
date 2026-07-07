# Plan 006: Give silhouette_scan the same English-decline behavior as its sibling scanners

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/silhouette_scan.py scripts/_lang.py evals/adversarial-evals.json`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (004 soft-recommended first)
- **Category**: bug
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

The product's one intentional refusal is a graceful English-only decline.
`scripts/_lang.py`'s own docstring says the scanners "must decline the same
non-English inputs" — and `banned_phrase_scan.py`, `structure_scan.py`, and
`suggest.py` all import it and decline. `silhouette_scan.py` does not import
`_lang` at all, yet SKILL.md lists any silhouette flag as a **blocking**
validation gate. Result: a Spanish document the other two scanners correctly
wave through with `{"non_english": true}` can still be hard-blocked by
silhouette metrics computed on tokens they were never validated for — a gate
disagreeing with its peers on exactly the input the product promises to
decline cleanly.

**Critical design constraint (learned the hard way in this repo)**: the
decline must be **scan-first**. An earlier bug (fixed at commit `4d514a2`)
had scanners declining BEFORE scanning; low-function-word English slop
(headline stacks, buzzword lists) was misclassified as non-English and waved
through. The pinned pattern: run the scan; decline as non-English only when
the language heuristic fails AND nothing flagged. Copy it exactly.

## Current state

- `scripts/silhouette_scan.py:380-394` (main, tail):
  ```python
      if args.path:
          path = Path(args.path)
          if not path.exists():
              print(f"Missing file: {path}", file=sys.stderr)
              return 2
          text = path.read_text()
      else:
          text = sys.stdin.read()

      result = scan(text, reference, args.genre)
      print(json.dumps(result, indent=2))
      is_flagged = bool(result.get("penalty") is not None
                        and result["penalty"] >= PENALTY_THRESHOLD)
      return 1 if is_flagged else 0
  ```
  No `_lang` import anywhere in the file (verify: `grep -n "_lang\|is_probably_english" scripts/silhouette_scan.py` → empty).
- The exemplar to copy — `scripts/structure_scan.py:301-307` (scan-first
  decline, after `result = scan(...)`):
  ```python
      if not result.get("flags") and not is_probably_english(text):
          print(json.dumps({"non_english": True, "violations": [], "flags": []}, indent=2))
          print("note: input appears non-English; scanner declined (English-only).", file=sys.stderr)
          return 0
  ```
  and its import block (`sys.path.insert(0, str(Path(__file__).resolve().parent))`
  then `from _lang import is_probably_english`) — read structure_scan's exact
  import lines and match them.
- Existing LANG rows in `evals/adversarial-evals.json`: ids starting `LANG-`
  pin decline behavior for the other scanners, including `LANG-3a` (headline
  stack must be SCANNED, not declined — the scan-first pin). Read them before
  writing yours.
- Silhouette output shape note: its JSON uses `penalty`/`flags`/metric keys,
  not `violations` — the decline JSON for silhouette should be
  `{"non_english": true, "flags": [], "penalty": null}` to stay
  consumer-compatible (confirm what keys downstream consumers read:
  `grep -rn "silhouette" SKILL.md references/commands/` — the blocking rule
  keys off `flags`/exit code).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| LANG slice | `python3 evals/run_adversarial.py --only LANG` | all pass |
| Silhouette gates | `python3 evals/check_silhouette.py --reference && python3 evals/check_silhouette.py --separation` | both green (byte-identical reference; 12/12 + 0/8) |
| Manual decline | `printf 'Hola amigo. ¿Cómo estás? Muy bien gracias. El perro corre en el parque todos los días.\n\nOtra párrafo en español con más palabras comunes del idioma.' \| python3 scripts/silhouette_scan.py` | after fix: non_english JSON, exit 0 |

## Scope

**In scope**: `scripts/silhouette_scan.py`; `evals/adversarial-evals.json`
(2-3 new LANG rows); `scripts/_lang.py` docstring only (update "both
scanners" → "all three scanners" — one line).

**Out of scope**: silhouette's metrics, reference stats, thresholds; the
other scanners; `evals/check_silhouette.py`.

## Git workflow

- Branch: `advisor/006-silhouette-decline`; rows red-first.

## Steps

### Step 1: Red rows

Add (next free LANG numbers):
1. Spanish prose (long enough to produce paragraphs; ≥2 paragraphs) into
   silhouette via stdin → assert exit 0, `stdout_contains: "non_english"`.
   RED today (silhouette scores it instead).
2. Scan-first pin, mirroring LANG-3a's intent: an English document that
   silhouette currently FLAGS (steal the structure of an existing AI-fixture
   doc from `evals/fixtures/` that the separation check flags — find one via
   `python3 evals/check_silhouette.py --separation` output naming flagged AI
   docs) but formatted to score LOW on the function-word heuristic is hard to
   construct; simpler equivalent pin: assert that a KNOWN-flagged English AI
   fixture still exits 1 (flags win over decline). Use a fixture path row:
   `["python3","scripts/silhouette_scan.py","evals/fixtures/silhouette/<flagged-doc>.md"]`
   → `exit_code: 1`. GREEN today and must STAY green — its role is to catch
   a wrong decline-first implementation. Mark its purpose in the title.

**Verify**: row 1 FAILS at HEAD, row 2 passes.

### Step 2: Implement scan-first decline

In `silhouette_scan.py` main, after `result = scan(...)` and before printing:

```python
    if not result.get("flags") and not is_probably_english(text):
        print(json.dumps({"non_english": True, "flags": [], "penalty": None}, indent=2))
        print("note: input appears non-English; scanner declined (English-only).", file=sys.stderr)
        return 0
```

with the import block copied from structure_scan (dual-mode safe). Update
`_lang.py`'s docstring sentence to name all three scanners.

**Verify**: LANG slice all green (including your new rows); manual decline
command produces non_english JSON; full suite green; both silhouette gates
green (reference must be BYTE-IDENTICAL — the decline path must not touch
scoring).

## Test plan

The two new LANG rows. Row 2 is the regression guard against the
decline-before-scan bug class this repo already met once.

## Done criteria

- [ ] Full suite exit 0, FAIL 0
- [ ] `python3 evals/run_adversarial.py --only LANG` all pass, incl. new rows
- [ ] `check_silhouette.py --reference` and `--separation` unchanged/green
- [ ] `grep -c "is_probably_english" scripts/silhouette_scan.py` ≥ 1
- [ ] `plans/README.md` updated

## STOP conditions

- structure_scan's import pattern doesn't transplant cleanly (dual-mode
  import error when running `python3 -c "from scripts.silhouette_scan import scan"`
  from repo root) — report the error, don't invent a new import scheme.
- The separation check changes in ANY digit — the decline branch somehow
  reached scoring; revert and report.
- Spanish fixture text keeps scoring flags (decline unreachable) — the
  fixture is then structurally slop-shaped by accident; adjust the fixture
  prose, not the threshold.

## Maintenance notes

- If a fourth scanner ever ships, `_lang.py`'s docstring and this decline
  parity are the checklist.
- Reviewer: confirm the decline JSON keys match what SKILL.md's blocking rule
  reads (flags/exit code), so a decline can never read as a block.
