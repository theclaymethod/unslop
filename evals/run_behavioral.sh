#!/usr/bin/env bash
set -euo pipefail

split="${1:-tune}"

if [[ "$split" == "holdback" && "${UNSLOP_CONFIRM_HOLDBACK:-}" != "1" ]]; then
  echo "Refusing to run sealed holdback split without UNSLOP_CONFIRM_HOLDBACK=1" >&2
  exit 2
fi

run_dir="runs/${split}"
tasks="${run_dir}/tasks.jsonl"
judge="${run_dir}/judge.jsonl"
fixed_judge="${run_dir}/judge.fixed.jsonl"
benchmark="${run_dir}/benchmark.json"

mkdir -p "$run_dir"

skill-benchmark prepare evals/shared-benchmark.json --split "$split" --out "$tasks"
python3 evals/run_local.py "$tasks" --jobs 5
skill-benchmark judge evals/shared-benchmark.json --runs "$run_dir" --split "$split" \
  --judge-cmd 'claude -p' --out "$judge"

python3 - "$judge" "$fixed_judge" <<'PY'
import json
import sys

source, dest = sys.argv[1], sys.argv[2]
rows = [json.loads(line) for line in open(source) if line.strip()]
for row in rows:
    if row.get("score") is None:
        row["score"] = 1.0 if row.get("passed") else 0.0
    row.setdefault("threshold", 1)
open(dest, "w").write("\n".join(json.dumps(row) for row in rows) + "\n")
PY

skill-benchmark benchmark evals/shared-benchmark.json --runs "$run_dir" --split "$split" \
  --allow-scripts --judge-results "$fixed_judge" --out "$benchmark"
