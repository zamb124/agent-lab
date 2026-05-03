#!/usr/bin/env bash
# Объединение GPU worker ноды в MicroK8s кластер.
# Запускать НА MASTER ноде (84.38.184.105) под root.
#
# Что делает:
#   1. Идемпотентно: SSH-ключ master → gpu-worker (для microk8s add-node + join).
#   2. Если gpu-worker уже в кластере → skip всех шагов join.
#   3. microk8s add-node — выпускает разовый токен.
#   4. SSH на gpu-worker → microk8s join <token> --worker (без datastore HA).
#   5. Дожидается gpu-worker Ready.
#   6. kubectl label node gpu-worker accelerator=nvidia-gpu (с --overwrite).
#
# Что НЕ делает: `microk8s enable gpu` / NVIDIA gpu-operator. Этот аддон ставит
# nvidia-container-toolkit-daemonset, который переписывает containerd config и
# выставляет disabled_plugins=["io.containerd.grpc.v1.cri"], валя kubelet
# (Unimplemented runtime.v1.RuntimeService). Вместо operator — простой
# NVIDIA k8s-device-plugin DaemonSet в Helm-чарте agent-lab
# (templates/50-gpu/nvidia-device-plugin.yaml). Host-driver + nvidia-container-toolkit
# уже настроен через bootstrap-gpu-worker.sh (drop-in /etc/containerd/conf.d/99-nvidia.toml).
#
# ENV:
#   GPU_WORKER_HOST   = root@188.246.224.228 (по умолчанию SSH_USER@GPU_HOST_IP из _common.sh)
#   GPU_NODE_NAME     = gpu-worker
#   GPU_NODE_LABEL_*  = accelerator=nvidia-gpu
#   JOIN_TIMEOUT      = 180

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command microk8s || exit 1
require_command ssh || exit 1

GPU_WORKER_HOST="${GPU_WORKER_HOST:-${SSH_USER}@${GPU_HOST_IP}}"
JOIN_TIMEOUT="${JOIN_TIMEOUT:-180}"

log_section "Join $GPU_NODE_NAME → cluster ($GPU_WORKER_HOST)"

# 0. Идемпотентно: убедиться что master может SSH-ом дойти до gpu-worker.
# Если ключа нет — генерим, public кладём в authorized_keys gpu-worker.
if [ ! -f /root/.ssh/id_ed25519 ]; then
  log_do "ssh-keygen ed25519 для root на master"
  install -d -m 700 /root/.ssh
  ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519 -C "root@$(hostname)-microk8s" >/dev/null
fi
MASTER_PUBKEY="$(cat /root/.ssh/id_ed25519.pub)"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "$GPU_WORKER_HOST" "true" 2>/dev/null; then
  log_warn "SSH master → $GPU_WORKER_HOST без ключа: добавьте pubkey master в authorized_keys gpu-worker."
  log_warn "Pubkey master:"
  printf '  %s\n' "$MASTER_PUBKEY"
  log_warn "Команда (с другой машины, у которой уже есть SSH к gpu-worker):"
  printf '  ssh %s "mkdir -p /root/.ssh && echo %q >> /root/.ssh/authorized_keys"\n' \
    "$GPU_WORKER_HOST" "$MASTER_PUBKEY"
  exit 1
fi
log_ok "SSH master → $GPU_WORKER_HOST"

# 1. Уже в кластере?
if microk8s kubectl get node "$GPU_NODE_NAME" >/dev/null 2>&1; then
  log_skip "node $GPU_NODE_NAME уже в кластере"
else
  # 2. Выпускаем токен и команду join
  log_do "microk8s add-node (получаем join команду)"

  ADD_NODE_OUT="$(microk8s add-node --token-ttl 7200 2>&1)"

  # microk8s add-node выводит несколько вариантов команды (worker, ipv4 only).
  # Берём первую содержащую "microk8s join" с IP мастера или 25000.
  JOIN_CMD="$(printf '%s\n' "$ADD_NODE_OUT" | grep -E 'microk8s join [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:25000/' | head -n1 | sed 's/^[[:space:]]*//')"

  if [ -z "$JOIN_CMD" ]; then
    log_error "Не удалось распарсить вывод 'microk8s add-node':"
    printf '%s\n' "$ADD_NODE_OUT" | sed 's/^/    /'
    exit 1
  fi

  log_info "Команда для worker: $JOIN_CMD"

  # 3. SSH на worker → join
  log_do "SSH $GPU_WORKER_HOST: $JOIN_CMD"
  if ! ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$GPU_WORKER_HOST" "$JOIN_CMD"; then
    log_error "SSH join упал. Проверьте ключи и доступность $GPU_WORKER_HOST"
    exit 1
  fi
fi

# 4. Дожидаемся Ready
wait_for \
  "node $GPU_NODE_NAME Ready" \
  "[ \"\$(microk8s kubectl get node $GPU_NODE_NAME -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}' 2>/dev/null)\" = 'True' ]" \
  "$JOIN_TIMEOUT" 5 \
  || exit 1

# 5. Лейбл (overwrite — идемпотентно). Helm чарт через nodeSelector accelerator=nvidia-gpu
# планирует provider-litserve и NVIDIA k8s-device-plugin DaemonSet на эту ноду.
log_do "label node $GPU_NODE_NAME $GPU_NODE_LABEL_KEY=$GPU_NODE_LABEL_VALUE"
microk8s kubectl label node "$GPU_NODE_NAME" "${GPU_NODE_LABEL_KEY}=${GPU_NODE_LABEL_VALUE}" --overwrite

# Финал
print_summary

log_section "Дальше"
cat <<EOF
1) Wildcard TLS (один раз):
   REGRU_USERNAME=... REGRU_PASSWORD=... bash $SCRIPT_DIR/setup-wildcard-tls.sh
2) Сохраните kubeconfig в GitHub Secret KUBECONFIG_B64:
   microk8s config | base64 -w0
3) Первый деплой (NVIDIA device-plugin DaemonSet входит в Helm-чарт):
   make k8s-secrets-sync   # из репо, после export всех нужных ENV
   make k8s-deploy IMAGE_TAG=latest
4) Проверка GPU в кластере:
   microk8s kubectl get node $GPU_NODE_NAME -o jsonpath='{.status.allocatable.nvidia\\.com/gpu}{"\\n"}'
   bash $SCRIPT_DIR/cluster-health.sh
EOF
