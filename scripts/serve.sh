#!/usr/bin/env bash
# Launch llama-server (CPU) for one GGUF model with parallel slots.
# Usage: scripts/serve.sh <model.gguf> <port> [n_parallel] [ctx_total]
set -euo pipefail
MODEL=${1:?gguf path}
PORT=${2:-8081}
NP=${3:-16}
CTX=${4:-98304}
LLAMA_DIR=${LLAMA_DIR:-/home/amit/llama.cpp/llama-b10839}
GOMP_DIR=${GOMP_DIR:-/home/amit/miniconda3/envs/deep/lib}
export LD_LIBRARY_PATH="$GOMP_DIR:$LLAMA_DIR:${LD_LIBRARY_PATH:-}"
LOG=/home/amit/llama.cpp/server_${PORT}.log
nohup "$LLAMA_DIR/llama-server" -m "$MODEL" --port "$PORT" --host 127.0.0.1 \
  -c "$CTX" -np "$NP" -t "$(nproc)" --jinja > "$LOG" 2>&1 &
echo "pid $! log $LOG"
for i in $(seq 1 120); do
  sleep 2
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" | grep -q '"ok"'; then echo "ready on :$PORT"; exit 0; fi
done
echo "server did not become healthy; see $LOG"; exit 1
