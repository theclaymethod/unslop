# Plan 007: Put wiki_sync's parser under eval coverage with an offline fixture

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/wiki_sync.py evals/`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (additive coverage; one seam refactor)
- **Depends on**: plans/004 (soft — schema gate validates new rows)
- **Category**: tests
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`scripts/wiki_sync.py` is the only script in the repo no eval row or gate
reaches (verified by grep across `evals/`, CI, CLAUDE.md). Yet it fetches and
parses external wikitext (Wikipedia's AI-writing-signs page) and proposes
edits to the authoritative phrase catalog (`references/taboo-phrases.md`) and
the scanner. If its parser or `SECTION_MAP` drifts against Wikipedia's markup,
it silently emits wrong diffs/prompts. The parsing path is pure and trivially
fixture-testable offline; only the fetch needs a seam.

## Current state

`scripts/wiki_sync.py` (verified at 217c218):
- `:56` `def fetch_latest_revision() -> tuple[int, str, str]:` — network,
  `urllib.request.urlopen(req, timeout=30)` at `:73`.
- `:106` `def parse_wikitext(wikitext: str) -> list[ParsedSection]:` — pure.
- `:246` `SECTION_MAP: dict[str, dict[str, str]] = {` — keyword→target
  mapping consumed at `:301`.
- `:357` `cmd_check`, `:380` `cmd_diff`, `:406` `cmd_prompt` — the three
  subcommands; each currently obtains wikitext via the network fetch.
- State file: `scripts/.wiki_sync_state.json` (per README) — commands may
  read/write it; the fixture path must not clobber real state (see step 2).
- Row/gate conventions: rows in `evals/adversarial-evals.json` with
  `target: "script"`, commands as argv lists; gates registered in
  `evals/run_adversarial.py::list_gates()` with CHECKS.md regen via
  `evals/check_gates_doc.py` (exemplar gate dict at `run_adversarial.py:188`).
- Fixture conventions: committed under `evals/fixtures/<area>/…` (see
  `evals/fixtures/harvest/` for an exemplar of fixture+rows pairing).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| Gate doc | `python3 evals/check_gates_doc.py` | ok |
| New rows | `python3 evals/run_adversarial.py --only WIKI` | pass after implementation |

## Scope

**In scope**: `scripts/wiki_sync.py` (add `--from-file` seam only — no parser
behavior change); new `evals/fixtures/wiki/snapshot.wikitext` (INVENTED
content, see step 1); `evals/adversarial-evals.json` (new WIKI-prefix rows);
optionally `evals/run_adversarial.py::list_gates()` + `evals/CHECKS.md` if
you add a named gate (rows alone are sufficient; a gate is optional polish —
skip if CHECKS regen is unclear).

**Out of scope**: any change to parse behavior, SECTION_MAP content, the
network path, `references/taboo-phrases.md`.

## Git workflow

- Branch: `advisor/007-wiki-sync-coverage`; rows red-first (they fail until
  the seam exists); sentence-case commits.

## Steps

### Step 1: Author the fixture

Create `evals/fixtures/wiki/snapshot.wikitext` — a ~60-line INVENTED wikitext
document exercising the parser's real branches. Read `parse_wikitext`
(`wiki_sync.py:106` onward) first and include one instance of each construct
it handles: section headers (`== … ==`), list items, bold/italic markup,
templates it strips, and at least two sections whose titles hit different
`SECTION_MAP` keywords (read the map at `:246` and use two real keywords),
plus one section matching nothing. Do NOT copy real Wikipedia text (license
noise + drift); invent content with distinctive marker phrases like
`WIKIFIXTURE_MARKER_ALPHA`.

**Verify**: `python3 -c "import sys; sys.path.insert(0,'scripts'); from wiki_sync import parse_wikitext; print(len(parse_wikitext(open('evals/fixtures/wiki/snapshot.wikitext').read())))"` → a section count > 0 matching your fixture's structure.

### Step 2: Add the offline seam

Add `--from-file PATH` to the CLI (argparse — the file already uses it;
match its subcommand wiring). When present, `cmd_check`/`cmd_diff`/
`cmd_prompt` read wikitext from PATH instead of fetching, and skip any state
writes that would record a fetched revision (read how
`.wiki_sync_state.json` is written; guard it behind "not from_file" so eval
runs never mutate real state — this is a STOP-worthy detail if state writes
are entangled with parsing).

**Verify**: `python3 scripts/wiki_sync.py diff --from-file evals/fixtures/wiki/snapshot.wikitext` → structured output, exit code per its convention, no network, and `git status` shows `.wiki_sync_state.json` unmodified.

### Step 3: Rows

Add WIKI-01..03 (new prefix; plan 004's schema gate — if landed — must accept
it: check its id regex): (1) `diff --from-file` on the fixture → exit code +
`stdout_contains` one mapped keyword marker; (2) `prompt --from-file` →
`stdout_contains` a marker proving section content reached the prompt; (3) a
negative: the unmapped section's marker does NOT appear in diff output
(`stdout_not_contains`). Assert `stderr_not_contains: "Traceback"` on all.

**Verify**: `python3 evals/run_adversarial.py --only WIKI` → 3 pass; full suite green.

## Test plan

The three WIKI rows. They pin: parser reaches mapped sections, prompt
rendering works, unmapped content stays out. Model row JSON on any HARV row.

## Done criteria

- [ ] Full suite exit 0, FAIL 0 (439+1 + 3 WIKI rows)
- [ ] `python3 evals/run_adversarial.py --only WIKI` → 3/3
- [ ] Offline run touches no network (run with network-less env if easy:
      `python3 scripts/wiki_sync.py diff --from-file …` completes < 2s)
- [ ] `.wiki_sync_state.json` untouched by eval runs (`git status`)
- [ ] `plans/README.md` updated

## STOP conditions

- `parse_wikitext` or the cmd_* functions are entangled with fetch/state in
  a way that needs more than a thin seam (e.g. revision ids threaded through
  parsing) — report the actual structure and a proposed seam instead of
  refactoring broadly.
- Plan 004's id regex rejects the WIKI prefix — coordinate: extend the regex
  in the same commit ONLY if 004 is already DONE; otherwise note it.

## Maintenance notes

- When Wikipedia's page structure changes for real, the fixture will NOT
  catch it (it pins the parser, not the world); the `check` subcommand
  against the live page remains the manual drift detector. A cron-ish
  refresh procedure is plan 013's territory.
- Reviewer: confirm the fixture is invented text, not copied wikitext.
