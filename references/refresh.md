# Adversarial refresh

The Growth section of `docs/PRODUCT.md` promises that detection catalogs
stay current through adversarial refresh. This page is the procedure. It is
what an agent runs to make that promise real. Nothing here runs on a
schedule (see `docs/DECISIONS.md`, "Agent-invoked only"); it runs when an
agent, or the person driving one, decides to check.

## 1. Check staleness

```bash
python3 scripts/refresh_status.py
```

Stdlib, offline, always exits 0. It reports three signals as JSON:

- `wiki_sync`: days since the local Wikipedia sync state was last updated.
- `parity_bench`: days since the model-parity matrix in
  `references/pipeline.md` was last recorded.
- `newest_pattern_row`: days since `evals/adversarial-evals.json` last
  gained a row.

Each carries `last` (an ISO date or `null`), `days` (or `null`), and a
`stale` flag; the script never fails a build over it, and the flag is a
prompt for judgment rather than a rule to obey mechanically. The thresholds
it applies (wiki 90 days, bench 180 days, rows 60 days) are commented in the
script itself as starting points.

## 2. If `wiki_sync` is stale

```bash
python3 scripts/wiki_sync.py check   # exit 0 = no updates, 1 = updates available
python3 scripts/wiki_sync.py diff    # structured JSON diff, when check exits 1
```

For each new word or phrase in the diff, follow "Add a banned phrase" in
`references/maintenance.md`: eval rows first, then the scanner, then the
catalog. Skip Wikipedia-specific patterns, such as broken wikitext, DOI
formatting, or citation graffiti. Only genuine AI tells in general prose
belong here.

## 3. If `parity_bench` is stale

Treat staleness as a prompt to double-check the recorded table against
reality. It is not an automatic re-run trigger by itself: the binding rule
in `references/pipeline.md` (Model Parity) already forces a re-run whenever
the co-writer, mimic, or detector-pack model features change, independent of
elapsed time. When a re-run is warranted, run the live matrix across both
spectrums:

```bash
python3 evals/run_model_parity.py --task both --format both
```

Update the tiering table and the "Recorded results" tables in
`references/pipeline.md` from the output, and update the standing
conclusions in `docs/PRODUCT.md`'s Model tiering section if they changed.
The `PARITY-*` rows in `evals/adversarial-evals.json` gate the grader itself
in dry-run mode. They do not substitute for the live run above:

```bash
python3 evals/run_model_parity.py --dry-run \
  --responses evals/fixtures/parity/canned_responses.json
```

## 4. Every miss becomes a row

A miss can come from a live bench output, a wiki-sync diff, or something
caught by hand. Whichever it is, route it through
`references/commands/contribute.md`. Contribute turns the exact specimen
into a red-first eval row and a structured PR, so the miss becomes a
permanent regression test instead of a one-off fix.

## 5. Record results

- Model-parity runs: update `references/pipeline.md`'s dated tables (the
  "Live matrix recorded **YYYY-MM-DD**" line and the two results tables
  under it) with the new date and numbers.
- Behavioral or skill runs: follow the conventions already set in
  `evals/TUNE-RESULTS.md`. Name the harness version, split, runner, and
  judge. Then report per-case deltas rather than aggregate lift, per
  `CLAUDE.md`'s Interpreting Results section.

## Cadence guidance

There is no scheduler. Use `refresh_status.py`'s thresholds as the trigger
for a manual or agent-invoked check instead: wiki sync roughly quarterly,
the parity bench roughly every six months (sooner on any model-feature
change, per the binding rule above), and a look at the eval catalog if two
months pass with no new row.
