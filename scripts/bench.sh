#!/bin/bash
# Run the SWE-bench agent with ONE model on several tasks, then validate
# each solution with the moulinette.
# Usage: scripts/bench.sh MODEL PROVIDER_URL TASK [TASK...]
#   TASK is the name of a task file in cache/ without .json (sympy-13480)
# Output: benchmark/<task>__<model>__runN.json and its .validation.txt
# Env: RUN=N (default 1), EXTRA_ARGS (more agent options)
set -u
MODEL="$1"
URL="$2"
shift 2
RUN="${RUN:-1}"
NAME="${MODEL//\//_}"
mkdir -p benchmark
for TASK in "$@"; do
    OUT="benchmark/${TASK}__${NAME}__run${RUN}.json"
    echo "=== $(date '+%H:%M:%S') $TASK with $MODEL -> $OUT"
    # --no-fallback: the run must measure this model only
    uv run python -m agent_swebench --task-file "cache/$TASK.json" \
        --output "$OUT" --model-name "$MODEL" --provider-url "$URL" \
        --no-fallback ${EXTRA_ARGS:-} 2> "$OUT.stderr.log"
    (cd moulinette && uv run moulinette_eval validate swebench \
        "../cache/$TASK.json" "../$OUT" 2>&1) \
        | grep -E "Resolution status|Correctness:|Metrics:|exceeds|Overall" \
        > "$OUT.validation.txt"
    echo "    $(grep Overall "$OUT.validation.txt")"
done
