#!/usr/bin/env bash
# Uso: ./run.sh <none|jitter> [numero_da_repeticao]
# Ex.: ./run.sh none 1 ; ./run.sh jitter 1
set -euo pipefail
MODE=${1:?uso: ./run.sh none|jitter [rep]}
REP=${2:-1}
export MITIGATION="$MODE" RUN_DIR="logs/${MODE}_run${REP}"
rm -rf "$RUN_DIR"; mkdir -p "$RUN_DIR"
docker compose up --build --abort-on-container-exit --exit-code-from client 2>&1 | tee "$RUN_DIR/compose_stdout.log"
docker compose down -v
python3 analyze.py "$RUN_DIR"
