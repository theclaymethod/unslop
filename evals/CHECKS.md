# Check Matrix

Run the repository checks with one command:

```bash
python3 evals/check.py
```

That command runs the authoritative adversarial suite once, verifies that the
generated behavioral benchmark is current, and validates strict leakage. The
adversarial suite already contains the category, documentation, coverage, pack,
schema, mimic, climb, and voice checks; do not rerun those slices as separate
release gates.

Use a slice only to diagnose a failure:

```bash
python3 evals/run_adversarial.py --only PREFIX
python3 evals/run_adversarial.py --case ID
```

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
    "id": "repository-check",
    "command": "python3 evals/check.py",
    "pass_criterion": "exit 0",
    "blocking": true,
    "needs": [
      "skill-benchmark"
    ]
  },
  {
    "id": "behavioral-tune",
    "command": "python3 evals/check.py --behavioral tune",
    "pass_criterion": "exit 0",
    "blocking": false,
    "needs": [
      "skill-benchmark",
      "claude -p"
    ]
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
