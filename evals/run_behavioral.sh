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

run_root="${UNSLOP_BEHAVIORAL_RUN_ROOT:-runs}"
cache_dir="${UNSLOP_BEHAVIORAL_CACHE_DIR:-${run_root}/.cache/behavioral}"
cache_identity="${UNSLOP_BEHAVIORAL_CACHE_IDENTITY:-}"
judge_identity="${UNSLOP_BEHAVIORAL_JUDGE_IDENTITY:-$cache_identity}"
if [[ "$cache_mode" != "off" && ( -z "$cache_identity" || -z "$judge_identity" ) ]]; then
  echo "cache mode requires UNSLOP_BEHAVIORAL_CACHE_IDENTITY (and optionally UNSLOP_BEHAVIORAL_JUDGE_IDENTITY)" >&2
  exit 2
fi

# The behavioral acceptance provider is intentionally pinned. Generation is
# dispatched by run_local with argv-safe provider selection; uncached judging
# uses the harness's native Codex backend, while cached judging wraps the same
# model_generate adapter for content-addressed reuse. Keeping these as
# constants prevents a stray shell environment value from silently changing
# the measured model.
model="gpt-5.6-luna"
judge_cmd="python3 evals/model_generate.py --kind codex --model $model"

run_dir="${run_root}/${split}"
tasks="${run_dir}/tasks.jsonl"
judge="${run_dir}/judge.jsonl"
fixed_judge="${run_dir}/judge.fixed.jsonl"
benchmark="${run_dir}/benchmark.json"
mkdir -p "$run_dir"

skill-benchmark prepare evals/shared-benchmark.json --split "$split" --out "$tasks"

runner_args=("$tasks" --jobs 5 --model "$model" --cache-mode "$cache_mode")
if [[ "$cache_mode" != "off" ]]; then
  runner_args+=(--cache-dir "${cache_dir}/generation" --cache-identity "$cache_identity")
fi
python3 evals/run_local.py "${runner_args[@]}"

if [[ "$cache_mode" != "off" ]]; then
  judge_cmd="python3 evals/cache_judge.py --cache-dir $(printf '%q' "${cache_dir}/judge") --identity $(printf '%q' "$judge_identity") --judge-cmd $(printf '%q' "$judge_cmd")"
  judge_args=(
    evals/shared-benchmark.json
    --runs "$run_dir"
    --split "$split"
    --judge-backend cmd
    --judge-cmd "$judge_cmd"
    --out "$judge"
  )
else
  # Native Codex judging keeps the uncached acceptance on the harness's
  # argv-safe provider path. The harness adds --output-last-message and
  # --output-schema itself, so no transcript parsing or shell command is
  # needed here.
  judge_args=(
    evals/shared-benchmark.json
    --runs "$run_dir"
    --split "$split"
    --judge-backend codex
    --judge-model "$model"
    --codex-cmd "codex exec"
    --out "$judge"
  )
fi
skill-benchmark judge "${judge_args[@]}"

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
