#!/usr/bin/env bash
# GPU base image must export llm-model (bitsandbytes) for CUDA chat LLM 4-bit load.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCKERFILE="${ROOT}/Dockerfile.base.gpu"

if ! grep -Fq 'llm-model' "${DOCKERFILE}"; then
  echo "check-gpu-dockerfile-llm-model: FAIL — Dockerfile.base.gpu must include --group llm-model"
  exit 1
fi

echo "check-gpu-dockerfile-llm-model: OK"
