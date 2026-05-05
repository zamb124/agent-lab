#!/usr/bin/env bash
# Снимок памяти GPU для планирования ёмкости LitServe (speech + Qwen RAG на одной карте).
# Запускайте на gpu-worker при нагрузке: параллельно STT/TTS, ingest (embedding) и search (rerank).
#
# Рекомендация: сравните idle, пик под смешанной нагрузкой и после прогрева моделей.

set -euo pipefail

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi не найден (нет NVIDIA driver / не GPU-нода)." >&2
  exit 1
fi

echo "# $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
nvidia-smi \
  --query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu,utilization.memory \
  --format=csv
