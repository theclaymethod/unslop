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
  cache_mode="${UNSLOP_BEHAVIORAL_CACHE_MODE:-read-write}"
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
jobs="${UNSLOP_BEHAVIORAL_JOBS:-2}"
if [[ ! "$jobs" =~ ^[1-9][0-9]*$ ]]; then
  echo "invalid UNSLOP_BEHAVIORAL_JOBS: $jobs" >&2
  exit 2
fi
cache_dir="${UNSLOP_BEHAVIORAL_CACHE_DIR:-${run_root}/.cache/behavioral}"
automatic_identity="behavioral-$(shasum -a 256 \
  evals/run_local.py evals/model_generate.py evals/cache_judge.py \
  | shasum -a 256 | cut -d ' ' -f 1)"
cache_identity="${UNSLOP_BEHAVIORAL_CACHE_IDENTITY:-$automatic_identity}"
judge_identity="${UNSLOP_BEHAVIORAL_JUDGE_IDENTITY:-$cache_identity}"

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

runner_args=("$tasks" --jobs "$jobs" --model "$model" --cache-mode "$cache_mode")
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
    # Boolean and scored verdicts are distinct harness schemas.  Do not mutate
    # a boolean into a scored verdict, and do not invent missing scored evidence.
    if row.get("verdict_kind") == "scored":
        if row.get("score") is None or row.get("threshold") is None:
            raise SystemExit(f"invalid scored judge verdict: {row.get('judge_task_id', '<unknown>')}")
open(dest, "w", encoding="utf-8").write("\n".join(json.dumps(row) for row in rows) + "\n")
PY

skill-benchmark benchmark evals/shared-benchmark.json --runs "$run_dir" --split "$split" \
  --allow-scripts --judge-results "$fixed_judge" --out "$benchmark"

# The harness reports metrics even when product cases fail.  The canonical
# wrapper is an acceptance command, so require every with-skill case to be
# complete and to clear every gate.  Baseline failures remain comparison data.
python3 - "$benchmark" "$tasks" <<'PY'
import json
import sys

benchmark_path, tasks_path = sys.argv[1:]
report = json.load(open(benchmark_path, encoding="utf-8"))
tasks = [json.loads(line) for line in open(tasks_path, encoding="utf-8") if line.strip()]
expected = {row["case_id"] for row in tasks if row.get("variant") == "with_skill"}
if not expected:
    print("behavioral acceptance failed: prepared tasks have no with-skill cases", file=sys.stderr)
    raise SystemExit(1)

failed = []
observed = []
for row in report.get("results", []):
    if row.get("variant") != "with_skill":
        continue
    observed.append(row.get("case_id"))
    if (
        row.get("missing_output")
        or row.get("execution_valid") is not True
        or row.get("combined_pass_rate") != 1.0
    ):
        failed.append(row.get("case_id", "<unknown>"))
observed_set = set(observed)
missing = expected - observed_set
unexpected = observed_set - expected
duplicates = {case_id for case_id in observed_set if observed.count(case_id) > 1}
if missing or unexpected or duplicates:
    details = []
    if missing:
        details.append("missing=" + ",".join(sorted(missing)))
    if unexpected:
        details.append("unexpected=" + ",".join(sorted(unexpected)))
    if duplicates:
        details.append("duplicate=" + ",".join(sorted(duplicates)))
    print("behavioral acceptance failed: result coverage mismatch (" + "; ".join(details) + ")", file=sys.stderr)
    raise SystemExit(1)
if failed:
    print("behavioral acceptance failed: " + ", ".join(sorted(set(failed))), file=sys.stderr)
    raise SystemExit(1)
print("behavioral acceptance passed: every with-skill case cleared every gate")
PY
