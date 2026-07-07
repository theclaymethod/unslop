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
