#!/usr/bin/env bash
# Полный reset MicroK8s на master: helm uninstall, kubectl delete namespace,
# snap remove microk8s --purge, удаление /var/snap/microk8s и nvidia containerd drop-in.
# Запускать с локальной машины. SSH: MASTER_HOST_IP. CONFIRM=0 (dry-run) | 1.
# NVIDIA driver не трогает. ytai.tech на 84.38.184.105 этим скриптом не трогать.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command ssh

NS="${K8S_NAMESPACE:-platform}"
REL="${K8S_RELEASE:-agent-lab}"
CONFIRM="${CONFIRM:-0}"

MASTER="${SSH_USER}@${MASTER_HOST_IP}"

log_section "Cluster reset (CONFIRM=$CONFIRM)"
log_info "master:  $MASTER"
log_info "namespace: $NS, release: $REL"

log_section "До reset: master snapshot"
ssh -o BatchMode=yes "$MASTER" "bash -s" <<EOF || log_warn "SSH master не отвечает"
echo '-- nodes --'
microk8s kubectl get nodes 2>/dev/null || echo "no microk8s"
echo '-- helm releases --'
microk8s helm3 list -A 2>/dev/null || true
echo '-- ns/$NS --'
microk8s kubectl get ns $NS 2>/dev/null || echo "no namespace $NS"
echo '-- snap --'
snap list microk8s 2>/dev/null || echo "no snap microk8s"
EOF

if [ "$CONFIRM" != "1" ]; then
  log_info "DRY-RUN: ничего не удалено. Для реального reset: CONFIRM=1 bash $0"
  exit 0
fi

log_section "Reset master"
ssh -o BatchMode=yes "$MASTER" "bash -s" <<EOF
set -uo pipefail

if microk8s helm3 list -n "$NS" 2>/dev/null | grep -q "^$REL "; then
  echo "[DO]    helm uninstall $REL -n $NS"
  microk8s helm3 uninstall "$REL" -n "$NS" --wait --timeout 5m 2>&1 | tail -10 || true
else
  echo "[SKIP]  helm release $REL отсутствует"
fi

if microk8s kubectl get ns "$NS" >/dev/null 2>&1; then
  echo "[DO]    kubectl delete ns $NS --wait=false"
  microk8s kubectl delete namespace "$NS" --wait=false --ignore-not-found=true || true
  for i in \$(seq 1 30); do
    if ! microk8s kubectl get ns "$NS" >/dev/null 2>&1; then break; fi
    sleep 3
  done
  if microk8s kubectl get ns "$NS" >/dev/null 2>&1; then
    echo "[WARN]  ns $NS висит в Terminating — снимаем finalizers"
    microk8s kubectl get ns "$NS" -o json 2>/dev/null \\
      | python3 -c 'import sys, json; d=json.load(sys.stdin); d["spec"]["finalizers"]=[]; print(json.dumps(d))' \\
      | microk8s kubectl replace --raw "/api/v1/namespaces/$NS/finalize" -f - 2>&1 | tail -3 || true
  fi
else
  echo "[SKIP]  namespace $NS отсутствует"
fi

if snap list microk8s 2>/dev/null | grep -q microk8s; then
  echo "[DO]    snap remove microk8s --purge"
  snap remove microk8s --purge 2>&1 | tail -5
else
  echo "[SKIP]  snap microk8s не установлен"
fi

if [ -d /var/snap/microk8s ]; then
  echo "[DO]    rm -rf /var/snap/microk8s"
  rm -rf /var/snap/microk8s
else
  echo "[SKIP]  /var/snap/microk8s отсутствует"
fi

if [ -f /etc/containerd/conf.d/99-nvidia.toml ]; then
  echo "[DO]    rm -f /etc/containerd/conf.d/99-nvidia.toml"
  rm -f /etc/containerd/conf.d/99-nvidia.toml
fi

echo "[OK]    master reset complete"
EOF

log_section "После reset"
ssh -o BatchMode=yes "$MASTER" 'snap list microk8s 2>/dev/null || echo "snap microk8s: REMOVED"; ls /var/snap/microk8s 2>&1 | head -3 || echo "/var/snap/microk8s: REMOVED"' | sed 's/^/    /'

print_summary
log_section "Дальше"
cat <<EOF
На master: bash $SCRIPT_DIR/bootstrap-master.sh
Локально: make k8s-deploy IMAGE_TAG=<sha>
EOF
