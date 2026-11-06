#!/usr/bin/env bash
# Final runs of the frozen third version (see FROZEN.txt). Same Ollama copies
# as the November reruns (num_ctx 32768, num_predict 2048).
cd "$(dirname "$0")"
mkdir -p logs
sha256sum -c FROZEN.txt --ignore-missing --quiet 2>/dev/null || { sha256sum sections_v3.py pipeline_v3.py prompts_v3.py run_v3.py | diff - <(grep -E '^[0-9a-f]{64}' FROZEN.txt) && echo ok || { echo "CODE CHANGED SINCE FREEZE"; exit 1; }; }
OLOG="$LOCALAPPDATA/Ollama/server.log"
trunc() { grep -c 'truncating input prompt' "$OLOG" 2>/dev/null || echo 0; }
run() {  # model short set
  local before=$(trunc)
  echo "=== $(date '+%F %T') start $2 set$3 (truncations so far: $before)"
  PHARMA_EXTRACTOR_MODEL=$1 python run_v3.py --set $3 --out "${2}_v3_set$3.xlsx" > "logs/${2}_v3_set$3.log" 2>&1
  echo "=== $(date '+%F %T') end $2 set$3 (exit $?, new truncations: $(( $(trunc) - before )))"
}
run qwen2.5-7b-ctx32k qwen A
run mistral-7b-ctx32k mistral A
run qwen2.5-7b-ctx32k qwen B
run mistral-7b-ctx32k mistral B
run llama3.1-8b-ctx32k llama B
echo "=== $(date '+%F %T') all done"
