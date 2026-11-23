#!/usr/bin/env bash
set -euo pipefail

MODE=${1:?uso: ./run.sh none|exp|jitter [rep]}
REP=${2:-1}

case "$MODE" in
    none|exp|jitter) ;;
    *) echo "Modo invalido: $MODE (use none, exp ou jitter)" >&2; exit 2 ;;
esac

# Windows (Git Bash) costuma ter so "python"; Linux/macOS, "python3".
PY=$(command -v python3 || command -v python)

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
"$PY" analyze.py "$RUN_DIR"
"$PY" summarize.py logs > /dev/null

echo "=== Concluido: logs e metricas em $RUN_DIR/ ==="
