#!/usr/bin/env bash
set -euo pipefail

split="${1:-tune}"
if [[ $# -gt 2 ]]; then
  echo "Usage: evals/run_behavioral.sh [tune|holdout|holdback] [--uncached]" >&2
  exit 2
fi
if [[ "${2:-}" == "--uncached" ]]; then
  cache_mode="off"
elif [[ -n "${2:-}" ]]; then
  echo "Usage: evals/run_behavioral.sh [tune|holdout|holdback] [--uncached]" >&2
  exit 2
else
  cache_mode="${UNSLOP_BEHAVIORAL_CACHE_MODE:-off}"
fi

if [[ "$split" == "holdback" && "${UNSLOP_CONFIRM_HOLDBACK:-}" != "1" ]]; then
  echo "Refusing to run sealed holdback split without UNSLOP_CONFIRM_HOLDBACK=1" >&2
  exit 2
fi
case "$cache_mode" in
  off|read-write) ;;
  *) echo "invalid UNSLOP_BEHAVIORAL_CACHE_MODE: $cache_mode" >&2; exit 2 ;;
esac

cache_dir="${UNSLOP_BEHAVIORAL_CACHE_DIR:-runs/.cache/behavioral}"
cache_identity="${UNSLOP_BEHAVIORAL_CACHE_IDENTITY:-}"
judge_identity="${UNSLOP_BEHAVIORAL_JUDGE_IDENTITY:-$cache_identity}"
model="${UNSLOP_BEHAVIORAL_MODEL:-}"
judge_model="${UNSLOP_BEHAVIORAL_JUDGE_MODEL:-}"
if [[ "$cache_mode" != "off" && ( -z "$cache_identity" || -z "$judge_identity" ) ]]; then
  echo "cache mode requires UNSLOP_BEHAVIORAL_CACHE_IDENTITY (and optionally UNSLOP_BEHAVIORAL_JUDGE_IDENTITY)" >&2
  exit 2
fi

run_dir="runs/${split}"
tasks="${run_dir}/tasks.jsonl"
judge="${run_dir}/judge.jsonl"
fixed_judge="${run_dir}/judge.fixed.jsonl"
benchmark="${run_dir}/benchmark.json"
mkdir -p "$run_dir"

skill-benchmark prepare evals/shared-benchmark.json --split "$split" --out "$tasks"

runner_args=("$tasks" --jobs 5 --cache-mode "$cache_mode")
if [[ -n "$model" ]]; then
  runner_args+=(--model "$model")
fi
if [[ "$cache_mode" != "off" ]]; then
  runner_args+=(--cache-dir "${cache_dir}/generation" --cache-identity "$cache_identity")
fi
python3 evals/run_local.py "${runner_args[@]}"

judge_cmd="claude"
if [[ -n "$judge_model" ]]; then
  judge_cmd+=" --model $(printf '%q' "$judge_model")"
fi
judge_cmd+=" -p"
if [[ "$cache_mode" != "off" ]]; then
  judge_cmd="python3 evals/cache_judge.py --cache-dir $(printf '%q' "${cache_dir}/judge") --identity $(printf '%q' "$judge_identity") --judge-cmd $(printf '%q' "$judge_cmd")"
fi
skill-benchmark judge evals/shared-benchmark.json --runs "$run_dir" --split "$split" \
  --judge-cmd "$judge_cmd" --out "$judge"

python3 - "$judge" "$fixed_judge" <<'PY'
import json
import sys

source, dest = sys.argv[1], sys.argv[2]
rows = [json.loads(line) for line in open(source, encoding="utf-8") if line.strip()]
for row in rows:
    if row.get("score") is None:
        row["score"] = 1.0 if row.get("passed") else 0.0
    row.setdefault("threshold", 1)
open(dest, "w", encoding="utf-8").write("\n".join(json.dumps(row) for row in rows) + "\n")
PY

skill-benchmark benchmark evals/shared-benchmark.json --runs "$run_dir" --split "$split" \
  --allow-scripts --judge-results "$fixed_judge" --out "$benchmark"
