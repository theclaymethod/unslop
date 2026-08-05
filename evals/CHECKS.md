# Check Matrix

Run the repository checks with one command:

```bash
python3 evals/check.py
```

That command runs the bounded core-contract lane: one core-outcome gate
containing exactly five high-signal offline examples. They exercise the Luna
runner interface, scorer, evidence rules, and acceptance gate without calling a
model. This is engineering evidence, not proof of product quality.
Generated-benchmark currency and strict leakage belong to the explicit
integrity phases in the behavioral/full lanes, not the normal edit loop.

Run the bounded deterministic safety and integrity lane explicitly when the
scanner, preservation validator, runner, or benchmark plumbing changes:

```bash
python3 evals/check.py --maintenance
```

The core-contract lane is intentionally budgeted at five examples. New
regression evidence belongs in the maintenance lane unless it changes one of
those five interfaces.

Run the core-contract lane, bounded deterministic maintenance matrix, and behavioral
integrity checks together before a release:

```bash
python3 evals/check.py --full
```

Use a slice only to diagnose a failure:

```bash
python3 evals/run_adversarial.py --only PREFIX
python3 evals/run_adversarial.py --case ID
```

The runner treats manifest rows as evidence inside three deterministic gates.
Scanner and preservation examples live in compact contract tables and run once
each. The expanded deterministic surface is still counted: the repository
fails if it exceeds 80 executable examples or 400 expanded outcome predicates,
or if a nested contract
wrapper hides another matrix. Use the explicit lane commands when you want the
product or maintenance scope:

```bash
python3 evals/run_adversarial.py --lane core-contract
python3 evals/run_adversarial.py --lane maintenance
```

Voice imitation, calibration, contribution tooling, and other authoring tools
are separate engineering-health scoreboards. They do not establish core
detection or repair quality and are not counted as product evidence. Run the
relevant scoreboard when that tool changes:

```bash
python3 evals/check_mimic.py --all
python3 evals/check_voice.py --all
python3 evals/check_climb.py --all
python3 evals/check_contrib.py --all
```

The `--group` form remains available for diagnosing one gate. `--only PREFIX`
and `--case ID` are diagnostic slices and do not enforce the product budget or
strict XFAIL set.

Script rows that mutate shared repository fixtures must declare
`"serial": true`; the runner completes all such rows before starting its
subprocess pool. `--eval-file PATH` supplies an isolated suite for runner
integration tests.

Behavioral checks are explicit and run after deterministic checks pass:

```bash
python3 evals/check.py --behavioral tune
```

The holdback split remains sealed unless
`UNSLOP_CONFIRM_HOLDBACK=1` is set.

`python3 evals/run_adversarial.py --list-gates` is the machine-readable
external gate surface:

```json
[
  {
    "id": "core-outcome",
    "command": "python3 evals/run_adversarial.py --group core-outcome",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": [],
    "lane": "core-contract",
    "budget": {
      "max_examples": 5
    }
  },
  {
    "id": "deterministic-safety",
    "command": "python3 evals/run_adversarial.py --group deterministic-safety",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": [],
    "lane": "maintenance",
    "budget": {
      "max_examples": null
    }
  },
  {
    "id": "integrity-and-tools",
    "command": "python3 evals/run_adversarial.py --group integrity-and-tools",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": [],
    "lane": "maintenance",
    "budget": {
      "max_examples": null
    }
  },
  {
    "id": "behavioral",
    "command": "python3 evals/check.py --behavioral tune",
    "pass_criterion": "exit 0",
    "blocking": false,
    "needs": [
      "skill-benchmark",
      "codex exec (gpt-5.6-luna)"
    ],
    "lane": "behavioral",
    "budget": {
      "max_examples": null
    }
  }
]
```

## Writing a New Check

A new `evals/check_*.py` script must use the shared import seam:

```python
from _check_support import ROOT, run, load_evals  # noqa: E402
```

Import scanner APIs only after adding `ROOT` to `sys.path`. Exit 0 on pass,
1 on a finding, and 2 when setup is broken. Add the check as an adversarial
script row so the full suite remains the single source of deterministic
coverage. Add a top-level gate only when the check cannot run inside the
adversarial suite.
