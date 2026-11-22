#!/usr/bin/env bash
set -euo pipefail

MODE=${1:?uso: ./run.sh none|jitter [rep]}
REP=${2:-1}

if ! command -v docker &> /dev/null || ! docker compose version &> /dev/null; then
    echo "Erro: Docker e Docker Compose v2 sao necessarios." >&2
    exit 1
fi

export MITIGATION="$MODE"
export RUN_DIR="logs/${MODE}_run${REP}"

rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR"

echo "=== Executando miniatura (modo=$MODE, repeticao=$REP) ==="
echo "Logs brutos serao gravados em: $RUN_DIR/"
docker compose up --build --abort-on-container-exit --exit-code-from client 2>&1 | tee "$RUN_DIR/compose_stdout.log"
docker compose down -v

echo "=== Gerando metricas ==="
python3 analyze.py "$RUN_DIR"

echo "=== Concluido: logs e metricas em $RUN_DIR/ ==="
