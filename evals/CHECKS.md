# Check Matrix

`python3 evals/run_adversarial.py --list-gates` is the source of truth for the
gate matrix. It emits machine-readable JSON with each gate's id, command,
pass criterion, blocking status, and external needs.

Current gates:

```json
[
  {
    "id": "adversarial-suite",
    "command": "python3 evals/run_adversarial.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "harvest-suite",
    "command": "python3 evals/run_adversarial.py --only HARV",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "contribute-suite",
    "command": "python3 evals/run_adversarial.py --only CONTRIB",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "calibrate-suite",
    "command": "python3 evals/run_adversarial.py --only CAL",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "shared-benchmark-check",
    "command": "python3 evals/build_shared_benchmark.py --check",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "strict-leakage-validate",
    "command": "skill-benchmark validate evals/shared-benchmark.json --strict-leakage",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": [
      "skill-benchmark"
    ]
  },
  {
    "id": "taboo-catalog-parity",
    "command": "python3 evals/check_taboo_parity.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "pattern-coverage",
    "command": "python3 evals/check_pattern_coverage.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "voice-scorer",
    "command": "python3 evals/check_voice.py --separation && python3 evals/check_voice.py --gi && python3 evals/check_voice.py --gaming && python3 evals/check_voice.py --profiles",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "add-pattern-kata",
    "command": "python3 evals/kata_add_pattern.py --run",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "command-router-parity",
    "command": "python3 evals/check_commands.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "seeded-docs",
    "command": "python3 evals/check_seeded_docs.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "paired-fixture-hygiene",
    "command": "python3 evals/check_pairs.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "mimic-logic",
    "command": "python3 evals/run_adversarial.py --only MIMIC --only CARD",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "pack-structure",
    "command": "python3 scripts/check_packs.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "behavioral-tune",
    "command": "evals/run_behavioral.sh tune",
    "pass_criterion": "exit 0",
    "blocking": false,
    "needs": [
      "skill-benchmark",
      "claude -p"
    ]
  },
  {
    "id": "banned-phrase-scan",
    "command": "python3 scripts/banned_phrase_scan.py < transformed.txt",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "structure-scan",
    "command": "python3 scripts/structure_scan.py < transformed.txt",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "silhouette-scan",
    "command": "python3 scripts/silhouette_scan.py < transformed.txt",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "silhouette-check",
    "command": "python3 evals/check_silhouette.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "validate-preservation",
    "command": "python3 scripts/validate_preservation.py original.txt transformed.txt",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "readability-metrics",
    "command": "python3 scripts/readability_metrics.py < transformed.txt",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "diff-check",
    "command": "python3 scripts/diff_check.py original.txt transformed.txt",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  },
  {
    "id": "rubric-judge",
    "command": "Judge transformed output against the skill rubric",
    "pass_criterion": "non-deterministic rubric pass",
    "blocking": false,
    "needs": [
      "rubric judge"
    ]
  },
  {
    "id": "evals-schema",
    "command": "python3 evals/check_evals_schema.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": []
  }
]
```

## Parallel Check Protocol

Each deterministic gate is independent and exits 0 or 1, so the checks are safe
to hand to separate small-context sub-agents. Category slices can run
concurrently with `python3 evals/run_adversarial.py --only PREFIX`; use that for
scanner, preservation, robustness, documentation, and recall audits.

Two gates are non-deterministic because they call an LLM judge: the behavioral
split (`behavioral-tune`) and the per-rewrite rubric score (`rubric-judge`).
Run them last, after every deterministic gate passes — the behavioral split via
`evals/run_behavioral.sh tune`.

The JSON matrix above must stay byte-equal to `--list-gates` output; DOC-03
enforces this, so update both together.

## Writing a New Check

New `evals/check_*.py` scripts pull `ROOT` and the shared helpers from
`evals/_check_support.py`. Skip that. Two patterns disappear once you import
from `_check_support` instead of writing your own copy by hand: a private
`ROOT = Path(__file__).resolve().parent.parent` line, and a local subprocess
`run()` wrapper that quietly drifts from the one every other check already
trusts. Here is the seam.

```python
from _check_support import ROOT, run, load_evals  # noqa: E402
sys.path.insert(0, str(ROOT))          # only when importing scripts.* directly
from scripts.banned_phrase_scan import scan_for_violations  # noqa: E402
```

`run()` shells out. `load_evals()` loads rows. Exit 0. Exit 1 on a finding.
Exit 2 means setup broke — a missing fixture, a bad flag, something the
caller needs to fix before the check can even run its assertions. Wire the
check into the gate list in `run_adversarial.py`, then refresh the matrix
pinned near the top of this file.
