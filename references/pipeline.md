# Tiered Execution Pipeline

The skill still works with one agent, but orchestrators should use the cheapest executor that can do each job.

## Tier 0: Deterministic Gates

Run first on the source text:

```bash
python3 scripts/banned_phrase_scan.py <<< "$INPUT"
python3 scripts/structure_scan.py <<< "$INPUT"
python3 scripts/extract_constraints.py <<< "$INPUT"
python3 scripts/readability_metrics.py <<< "$INPUT"
```

Run again on output:

```bash
python3 scripts/banned_phrase_scan.py <<< "$OUTPUT"
python3 scripts/structure_scan.py <<< "$OUTPUT"
python3 scripts/validate_preservation.py original.txt transformed.txt
python3 scripts/readability_metrics.py <<< "$OUTPUT"
python3 scripts/diff_check.py original.txt transformed.txt
```

Output gates are blocking. Use `structure_scan.py --genre docs` or `--genre social` only when the final text truly belongs to that genre.

## Tier 1: Small Detector Agents

Run one small detector per `(pack x chunk)`. Use paragraph chunks up to about 500 words. Run `pack-register-guards` on the whole text because scope, negation, and legal/security force need context.

Detector agents only read their assigned pack from `references/packs/` and return findings:

```json
{"span":"...","rule":"...","pack":"...","severity":"hard|soft","note":"..."}
```

They do not rewrite, score, or import rules from other packs.

## Tier 2: Rewriter

Send one strong-enough rewriter the original text, merged Tier 0/Tier 1 findings, extracted constraints, and the selected preset. It rewrites from findings instead of re-running detection in prose. It must preserve register-guard and fact findings, remove phrase/structure/voice findings, and avoid introducing anti-slop-register tells.

## Model Tiers

| Job | Default executor | Escalate when |
|---|---|---|
| Tier 0 scripts | local deterministic | never; fix the script or input |
| Detection packs | cheapest tier (see Model Parity) | JSON is malformed or pack scope is violated |
| Span replacement / short rewrite | cheapest tier; gates carry safety (parity 2026-07-06: 8/8) | output fails a blocking gate twice |
| Full rewrite of register-sensitive text (legal, medical, security, load-bearing hedges) | strongest practical model + mandatory Tier-0 re-scan | start here; cheap tiers erode register |
| Macro structure (restructuring, coda/preview removal) | machine-gated AND machine-corrected via the structure climb (generate→scan→directive→regenerate); both frontier tiers converge fast, cheapest-that-converges is model-dependent (Anthropic haiku-4-5 at a slightly larger round cap; OpenAI's cheap tier not yet shown to converge) | never trust a model's own macro self-check — feed the scanners' directives back and re-scan (see Macro structure under the climb) |
| Judge/eval | model specified by `evals/BEHAVIORAL-EVALS.md` | benchmark protocol changes |

The model-dependent rows above are not set by taste. They are set by
`evals/run_model_parity.py` (see Model Parity), whose live matrix was recorded 2026-07-06:
span replacement clears on the cheapest tier because the output gates carry safety, while
full rewrites of register-sensitive text and any macro restructuring escalate to the
strongest practical model with a Tier-0 re-scan. Re-run the harness when the model features
change and update these rows from its output.

If Tier 2 output fails the same blocking gate twice, escalate one model tier. Do not add more rules to the prompt; the failure is execution quality.

## Model Parity

The pipeline depends on a model in exactly two places: Tier-1 pack **detection** and
Tier-2 **replacement** generation. Everything else is deterministic. Whether a cheap model
may own those surfaces is a measured question, not an assumption.

`evals/run_model_parity.py` measures it against a fixed seeded corpus:

- **Task A (detection).** Each model reads one pack file plus a short seeded chunk (the
  Tier-1 contract above) and returns JSON findings. Grading is deterministic: recall of the
  seeded findings and a count of false findings, scored against a frozen manifest. Six
  fixtures span the phrases-core, voice, and register-guard families (two are register-guard
  cases, where the load-bearing hedge must be caught).
- **Task B (replacement).** Each model is handed one seeded finding (span + rationale) and
  asked for a span-minimal replacement. Grading applies the co-writer contract: the
  replacement removes the flagged tell and adds no new one (both scanners), preserves every
  fact/number/negation, and stays span-minimal.

The matrix is config-driven — entries are `{name, kind, model_id}` where `kind` is
`claude-cli` (`claude -p --model <id>`, the Anthropic spectrum) or `openrouter` (the GPT
spectrum and others, key read from the macOS keychain service `OPENROUTER_API_KEY`). The
harness emits a per-model / per-task score table (JSON and a markdown summary) plus a
`--dry-run` mode that grades canned response fixtures with no network for the `PARITY-*`
eval rows.

**Rule (binding).** Any change to the co-writer, mimic, or detector-pack model features
must run this harness across both the GPT and Anthropic spectrums before merge, and the
detection/replacement rows of the tiering table above must be updated from its output. If
cheap models match the strong reference, use cheap everywhere; if they do not, keep the
strong model for the passes where the gap appears and record which. The `PARITY-*` rows in
`evals/adversarial-evals.json` gate the grader itself (dry-run, no network); they do not
substitute for the live run.

### Recorded results

Live matrix recorded **2026-07-06**. `evals/run_model_parity.py` re-measures on demand;
rerun it after any change to the co-writer, mimic, or detector-pack model features and
update these tables from its output.

**Task B — span replacement.** One seeded finding (span + rationale) per trial, graded on
the co-writer contract: the replacement removes the flagged tell, adds no new one (both
scanners), preserves every fact/number/negation, and stays span-minimal. Eight seeded
findings per model.

| Model | Kind | Task B pass rate |
|---|---|---:|
| claude-haiku | claude-cli | 8/8 |
| claude-sonnet | claude-cli | 8/8 |
| gpt-5.4-mini | openrouter | 8/8 |
| gpt-5.5 | openrouter | 8/8 |
| claude-opus | claude-cli | 7/8 |

The single miss was opus dropping the fact "8:30" from a replacement — caught by
`validate_preservation`, not by model choice. On the mechanical span contract the cheapest
tier ties the flagships; the gates carry safety, the tier does not.

**Behavioral parity matrix — full rewrites.** Eight register/structure cases per model,
graded deterministically across both the Anthropic and GPT spectrums.

| Model | Kind | Full-rewrite pass rate |
|---|---|---:|
| claude-opus | claude-cli | 7/8 |
| gpt-5.4-mini | openrouter | 7/8 |
| claude-sonnet | claude-cli | 6/8 |
| gpt-5.5 | openrouter | 6/8 |
| claude-haiku | claude-cli | 5/8 |
| gpt-5.4-nano | openrouter | 5/8 |

`MACRO-01` (`structure_clean`) failed for all six models, opus included: each kept a
conclusion coda the prose instruction told it to drop. No model self-checks macro structure
from prose. The cheap-tier misses were register and fact erosion in full rewrites — softened
`never`/`all`, a dropped `roughly`, a dropped legal `arguably`/negation, an emitted
`X, not Y` contrastive tail. The lab ladders are symmetric (7/6/5 on both spectrums).

**Measured conclusions.**

- **Span replacement = cheapest tier, with gates on.** The output gates enforce fact and
  tell safety, so the smallest model is safe for span-minimal replacement.
- **Full rewrites of register-sensitive text = frontier.** Legal, medical, security, or any
  text with load-bearing hedges/negation goes to the strongest practical model with a
  mandatory Tier-0 re-scan; cheap models erode register in unsupervised full rewrites.
- **Macro structure = always machine-gated, never self-checked — but machine-correctable.**
  A Tier-0 scan surfaces it as an explicit directive, because no model, flagship included,
  reliably catches it from prose instructions. Fed those directives back in a scan-regenerate
  loop (`evals/run_structure_climb.py`), both frontier tiers converge to clean fast; whether
  the cheap tier converges is model-dependent, not a uniform "cheap tier" property -- see
  "Macro structure under the climb" for the recorded before/after and the follow-up
  experiments.

### Open-weights spot check — 2026-07-07

Live matrix run against the current open-weights flagships of three Chinese labs, each the
newest general chat release of its family on OpenRouter: DeepSeek V4 Pro
(`deepseek/deepseek-v4-pro`), Kimi K2.6 (`moonshotai/kimi-k2.6`), and GLM 5.2
(`z-ai/glm-5.2`). Same harness and contracts as above; six detection fixtures (Task A) and
six replacement fixtures (Task B) per model. Models file:
`evals/fixtures/parity/models_openweights.json`.

| Model | Kind | Task A mean recall | Task A false findings | Task B pass rate |
|---|---|---:|---:|---:|
| glm-5.2 | openrouter | 1.00 | 0 | 6/6 |
| deepseek-v4-pro | openrouter | 0.92 | 1 | 6/6 |
| kimi-k2.6 | openrouter | 0.92 | 0 | 6/6 |

All three clear the span-replacement contract at 6/6, and the only detection misses were
one seeded voice span apiece (fixture A4) for DeepSeek and Kimi; on both model-dependent
surfaces the open-weights flagships sit level with the recorded GPT and Anthropic ladders.

## Macro structure under the climb — 2026-07-07

The recorded parity matrix above closed on a flat verdict: single-pass macro-structure
self-checking failed on every model. Told in prose to drop the coda / connective scaffold /
outline echo, each one shipped it anyway. But the deterministic scanners SEE those failures
precisely, so the failure is correctable even when it is not self-checkable. `evals/run_structure_climb.py`
closes that loop:

    generate -> scan (structure_scan + silhouette_scan) -> if clean, done
             -> else turn each finding into a TARGETED directive that names WHERE and
                WHAT -> feed the directives + current draft back -> regenerate, capped at
                N rounds (default 4).

The core is the **directive builder** (`build_directives`): a deterministic map from scanner
findings to instructions that locate the tell, because the model cannot see it. It re-reads
the draft with the scanners' own helpers, so a `conclusion_coda` flag becomes *"the final
paragraph (`Ultimately, ...`) restates the opening; end on a new fact"*, a
`connective_paragraph_openers` flag names the offending paragraph numbers and their opener
words, and a silhouette `callback_content` flag names the exact opening vocabulary the ending
loops back to. Every macro flag both scanners can emit maps to a directive (gated by
`CLIMB-06`). A preservation guard (`validate_preservation`, anchored to `--source-file` when
given) validates every round, so climbing toward clean structure can never eat a fact; a
regression aborts the climb. Honest terminal states (`converged` / `capped` /
`preservation_violation`) carry distinct exit codes. The mock path (`CLIMB-*` rows,
`evals/fixtures/climb/`) exercises all of this offline; the live path drives real models via
`--generate-cmd`.

Live run on the same `SKILL-MACRO-01` robotics-essay fixture as Task C, `--max-rounds 4`,
preservation anchored to the source essay:

| Model | Tier | Single pass (round 0) | Climbed | Rounds | Terminal | Facts |
|---|---|---|---|---:|---|---|
| claude-sonnet-4-5 | frontier | dirty: `signpost_density`, `callback_content` (penalty 7.5) | both scanners clean | 3 | converged | preserved every round |
| claude-haiku-4-5 | cheap | dirty: `callback_content` (penalty 2.5) | 1 residual structure flag | 4 | capped | preserved every round |
| gpt-5.5 | frontier | pending | pending | n/a | pending (OpenRouter HTTP 402) | pending |
| glm-5.2 | open-weights | pending | pending | n/a | pending (OpenRouter HTTP 402) | pending |

Read honestly:

- **Single pass ships macro tells on both Claude tiers**, reconfirming the thesis: told to
  remove macro tells, the model does not catch its own document shape.
- **The climb recovers macro on the frontier model where the single pass failed.** Sonnet
  converged to both-scanners-clean in three rounds (violation trajectory 2 → 1 → 0) with every
  fact preserved. This is the doctrine headline: with the loop, macro structure becomes
  machine-*corrected*, a step past machine-*gated*.
- **On the cheap tier the recovery is partial, not full.** haiku-4-5 consumed the silhouette
  recap loop on the first directive and held silhouette clean from round 1 on, but it
  oscillated on surface structure (re-introducing a coda, then a uniform cadence) and did not
  converge within four rounds, capping at one residual structure flag. The loop improves the
  cheap tier but does not guarantee it at cap 4; a residual macro flag on a cheap model still
  routes to a stronger model or another round, not to shipping.
- **The preservation guard held live throughout** (source-anchored): no round on either model
  eroded a fact.
- **The OpenRouter spectrum (GPT + open-weights) is pending on account billing** (HTTP 402
  Payment Required at run time), not on the harness. Exact reproduction commands:

  ```bash
  # Anthropic spectrum (native claude -p; run above):
  python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
    --out out/haiku --generate-cmd "claude -p --model claude-haiku-4-5" --max-rounds 4
  # OpenRouter spectrum (needs OPENROUTER_API_KEY credit):
  python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
    --out out/gpt --generate-cmd "python3 evals/model_generate.py --kind openrouter --model openai/gpt-5.5" --max-rounds 4
  python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
    --out out/glm --generate-cmd "python3 evals/model_generate.py --kind openrouter --model z-ai/glm-5.2" --max-rounds 4
  ```

### Two follow-up experiments — 2026-07-07

The OpenRouter 402 blocked the GPT spectrum above, and the cap-4 haiku row left one open
question (does the cheap tier ever converge, or does it just stall). Two follow-ups, both run
against the identical `SKILL-MACRO-01` fixture and source-anchored preservation:

**A. A local alternative to OpenRouter for the GPT side.** The `codex` CLI (OpenAI's agentic
coding CLI) is installed locally and can drive one model call per round the same way
`claude -p` does, sidestepping the billing block. `codex exec` is an AGENT CLI, though: its
stdout is an interleaved transcript (tool calls, hook lines, token counts), not a clean
document, so it cannot be piped straight into the climb loop. Its `-o/--output-last-message
FILE` flag writes only the agent's final text turn with no wrapping -- verified by hand against
this fixture before wiring it in. `evals/model_generate.py` gained a `codex` kind
(`call_codex`) that runs `codex exec --sandbox read-only --ephemeral --skip-git-repo-check -o
FILE -m <model> -`, reads that file, and discards the transcript. KNOWN RISK: `codex exec` has
been observed to hang silently in this environment; `call_codex` runs it in its own process
group with a hard wall-clock timeout (180s default) and SIGKILLs the whole group on expiry, so
a hang surfaces as an honest failed round instead of blocking the climb forever. `CLIMB-07`
exercises this offline against a fake `codex` binary (success, nonzero-exit, empty-output, and
hang paths; the hang case is SIGKILLed in about a second against a 1s test timeout).

**B. Does the cheap Anthropic tier ever converge, or does cap 4 just cut it off early.**
`claude-haiku-4-5` re-run with `--max-rounds 8` (same fixture, same generator) to see whether
the one residual flag at cap 4 was a hard ceiling or a round short.

Results, same fixture and settings as the recorded matrix above except where noted:

| Model | Tier | Kind | Single pass (round 0) | Climbed | Rounds (cap) | Terminal | Facts |
|---|---|---|---|---|---:|---|---|
| gpt-5.5 | frontier | codex exec (default model) | dirty: `sentence_burstiness`, `conclusion_coda`, `preview_fulfillment`, `callback_content` (4 flags) | both scanners clean | 4 (4) | converged | preserved every round |
| gpt-5.4-mini | cheap | codex exec | dirty: `sentence_burstiness`, `opener_repetition`, `preview_fulfillment`, `callback_content` (4 flags) | 2 residual flags, oscillating (4 → 1 → 5 → 2) | 4 (4) | capped | preserved every round |
| gpt-5.4-mini | cheap | codex exec, retried | dirty: `sentence_burstiness`, `preview_fulfillment`, `callback_content` (3 flags) | 5 residual flags, oscillating (3 → 3 → 2 → 1 → 6 → 2 → 1 → 5) | 8 (8) | capped | preserved every round |
| claude-haiku-4-5 | cheap | claude-cli, retried | dirty: `callback_content` (1 flag) | both scanners clean | 5 (8) | converged | preserved every round |

Read honestly:

- **The `-o` extraction is clean and codex is a real generator for this loop.** No stray
  transcript text ever reached the scanners; every round's draft was bare prose. `gpt-5.5`
  through `codex exec` converged in the same 4-round budget sonnet used (3 rounds), matching
  the frontier-converges finding on the Anthropic side.
- **Codex's cheap tier does not converge, even given double the round budget.** `gpt-5.4-mini`
  was run twice -- once at the recorded cap of 4, once at cap 8 -- and never reached clean
  either time. Its violation trajectory does not fall monotonically the way sonnet's or
  haiku's did; it swings between 1 and 6 flags round to round. The loop still holds every fact
  (preservation passed all 12 rounds across the two runs), but macro structure on this model
  is not machine-*correctable* at any round budget tested here, only machine-*gated*.
- **The cheap Anthropic tier was one round short of converging, not permanently capped.**
  `claude-haiku-4-5` re-run at `--max-rounds 8` converged in 5 rounds (violation trajectory
  1 → 1 → 1 → 1 → 0), the same residual `callback_content` flag from the cap-4 run finally
  clearing once the loop got one more pass. Every round preserved every fact.
- **This changes the doctrine.** "Cheap tiers partially recover" (the prior wording) was true
  of the one cheap model measured so far, but it is not a property of "cheap" in general --
  it is model-dependent. `claude-haiku-4-5` fully recovers with a slightly larger round cap;
  `gpt-5.4-mini` does not recover with an even larger one. Read the two model families
  separately, not as one "cheap tier" line.
- **Cheapest model that does this well: `claude-haiku-4-5`, with `--max-rounds` raised from 4
  to 6** (5 rounds measured to converge here; 6 gives one round of margin). On the GPT side,
  the floor that has actually been shown to converge is `gpt-5.5` (frontier) via codex, not
  `gpt-5.4-mini` -- the OpenAI cheap tier is not yet a substitute for this task on this
  evidence.
- **The OpenRouter spectrum itself (`gpt-5.5` via API, and `glm-5.2`) is still pending on
  account billing** (HTTP 402), not on the harness. Codex gave a working local alternative for
  measuring OpenAI's frontier and cheap models on this task, but it drives the model through
  Codex's own agent scaffolding and system prompt, not the raw chat-completions endpoint --
  read the codex-CLI numbers above as "the GPT models, as codex CLI calls them," not as an
  exact stand-in for a raw OpenRouter measurement once billing clears. `glm-5.2` has no local
  CLI alternative and remains unmeasured.

Exact reproduction commands:

```bash
# Anthropic spectrum, cheap tier, extended round cap:
python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
  --out out/haiku8 --generate-cmd "claude -p --model claude-haiku-4-5" --max-rounds 8
# Codex CLI, GPT spectrum (frontier default, then cheapest):
python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
  --out out/codex-gpt5.5 --generate-cmd "python3 evals/model_generate.py --kind codex --model gpt-5.5" --max-rounds 4
python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
  --out out/codex-mini --generate-cmd "python3 evals/model_generate.py --kind codex --model gpt-5.4-mini" --max-rounds 8
# OpenRouter spectrum (still needs OPENROUTER_API_KEY credit; unchanged from above):
python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
  --out out/gpt --generate-cmd "python3 evals/model_generate.py --kind openrouter --model openai/gpt-5.5" --max-rounds 4
python3 evals/run_structure_climb.py --prompt-file <macro-prompt> --source-file <essay> \
  --out out/glm --generate-cmd "python3 evals/model_generate.py --kind openrouter --model z-ai/glm-5.2" --max-rounds 4
```

## Cost Note

For a 1000-word document:

| Path | Calls | Approx tokens |
|---|---:|---:|
| Tier 0 | local scripts | free |
| Tier 1 | about 5 small detector calls | about 10k small-model tokens |
| Tier 2 | one rewrite call | source + findings + preset |
| Monolithic | one large call with full skill and all references | often 8k-15k strong-model tokens before output |

The tiered path spends cheap tokens on detection, reserves the stronger model for rewriting, and gives the final Tier 0 gates authority.
