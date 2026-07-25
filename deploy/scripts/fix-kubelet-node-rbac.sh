#!/usr/bin/env bash
# Идемпотентно восстанавливает ClusterRoleBinding system:node → Group system:nodes.
#
# В современных Kubernetes subjects у system:node часто пустые (права ожидаются от
# Node authorizer). Если Node authorizer/informers деградируют, kubelet получает
# Forbidden на list/watch nodes и pods → новые Pod навсегда Pending, Deploy DNS Job
# таймаутится (0 Active pods).
#
#   bash deploy/scripts/fix-kubelet-node-rbac.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

if [ -z "${KUBECTL:-}" ]; then
  log_error "kubectl недоступен — нужен KUBECONFIG"
  exit 1
fi

K="$KUBECTL"

log_section "Kubelet Node RBAC (system:node → system:nodes)"

if ! $K get clusterrolebinding system:node >/dev/null 2>&1; then
  log_error "ClusterRoleBinding system:node отсутствует"
  exit 1
fi

subjects="$($K get clusterrolebinding system:node -o jsonpath='{range .subjects[*]}{.kind}/{.name}{"\n"}{end}' 2>/dev/null || true)"
if printf '%s\n' "$subjects" | grep -qx 'Group/system:nodes'; then
  log_skip "system:node уже содержит Group/system:nodes"
  print_summary
  exit 0
fi

log_do "ClusterRoleBinding system:node: добавить Group/system:nodes"
cat <<'EOF' | $K apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: system:node
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:node
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: system:nodes
EOF

log_ok "system:node → system:nodes восстановлен"
print_summary
