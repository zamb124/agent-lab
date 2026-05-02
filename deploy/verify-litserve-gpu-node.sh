#!/usr/bin/env bash
# Проверка на хосте ноды после `docker compose -f docker-compose-litserve.yaml up`.
# Из каталога /opt/agent-lab (где compose и доступен доступ к GHCR-сокету).

set -euo pipefail

cd "$(dirname "$0")/.."

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -L || true
fi

compose_file="${COMPOSE_FILE:-docker-compose-litserve.yaml}"
service="${LITSERVE_SERVICE:-provider_litserve}"

docker compose -f "$compose_file" exec -T "$service" python -c '
import torch
ok = torch.cuda.is_available()
print("torch.cuda.is_available:", ok)
print("torch.version.cuda:", torch.version.cuda)
if ok:
    print("device:", torch.cuda.get_device_name(0))
assert ok, (
    "В контейнере LitServe недоступна CUDA: хост-драйвер, "
    "NVIDIA Container Toolkit и блок GPU в compose."
)
'

echo "verify-litserve-gpu-node: OK"
