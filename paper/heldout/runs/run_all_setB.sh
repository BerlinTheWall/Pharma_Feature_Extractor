#!/usr/bin/env bash
# Full-context reruns (Nov 2026). Models are Ollama copies with num_ctx 32768
# and num_predict 2048 (see modelfiles/), because the default context on this
# 6 GB GPU (4096 tokens) cut long sections off.
# Set B (held-out) first, then Set A (development) for Qwen and Mistral.
cd "$(dirname "$0")"
mkdir -p logs
OLOG="$LOCALAPPDATA/Ollama/server.log"
trunc() { grep -c 'truncating input prompt' "$OLOG" 2>/dev/null || echo 0; }

run() {  # model short set variant
  local before=$(trunc)
  echo "=== $(date '+%F %T') start $2 set$3 $4 (truncations so far: $before)"
  PHARMA_EXTRACTOR_MODEL=$1 python run_setB.py --set $3 --variant $4 --out "${2}_${4}_set$3.xlsx" > "logs/${2}_${4}_set$3.log" 2>&1
  local rc=$?
  echo "=== $(date '+%F %T') end $2 set$3 $4 (exit $rc, new truncations: $(( $(trunc) - before )))"
}

for m in "qwen2.5-7b-ctx32k qwen" "mistral-7b-ctx32k mistral" "llama3.1-8b-ctx32k llama"; do
  set -- $m
  for v in v1 v2; do run $1 $2 B $v; done
done
for m in "qwen2.5-7b-ctx32k qwen" "mistral-7b-ctx32k mistral"; do
  set -- $m
  for v in v1 v2; do run $1 $2 A $v; done
done
echo "=== $(date '+%F %T') all done"
