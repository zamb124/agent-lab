#!/usr/bin/env bash
# Общая библиотека идемпотентных хелперов для всех скриптов deploy/scripts/.
# Каждый скрипт начинается с:  source "$(dirname "$0")/_common.sh"

# shellcheck disable=SC2034

set -uo pipefail

# Цвета (если stdout — терминал, иначе пусто).
if [ -t 1 ]; then
  C_RED=$'\033[0;31m'
  C_GREEN=$'\033[0;32m'
  C_YELLOW=$'\033[0;33m'
  C_BLUE=$'\033[0;34m'
  C_DIM=$'\033[2m'
  C_RESET=$'\033[0m'
else
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_DIM=''; C_RESET=''
fi

# Состояние идемпотентности (заполняется log_*).
__SKIP_COUNT=0
__DO_COUNT=0
__FAIL_COUNT=0

log_info() {
  printf '%s[INFO]%s  %s\n' "$C_BLUE" "$C_RESET" "$*"
}

log_skip() {
  __SKIP_COUNT=$((__SKIP_COUNT + 1))
  printf '%s[SKIP]%s  %s\n' "$C_DIM" "$C_RESET" "$*"
}

log_do() {
  __DO_COUNT=$((__DO_COUNT + 1))
  printf '%s[DO]%s    %s\n' "$C_YELLOW" "$C_RESET" "$*"
}

log_ok() {
  printf '%s[OK]%s    %s\n' "$C_GREEN" "$C_RESET" "$*"
}

log_warn() {
  printf '%s[WARN]%s  %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2
}

log_error() {
  __FAIL_COUNT=$((__FAIL_COUNT + 1))
  printf '%s[ERROR]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2
}

log_section() {
  printf '\n%s===%s %s\n' "$C_BLUE" "$C_RESET" "$*"
}

# require_command kubectl - падаем с понятным сообщением если нет утилиты.
require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_error "Утилита '$cmd' не найдена в PATH"
    return 1
  fi
}

# require_root - убедиться, что запущено под root (для bootstrap скриптов на нодах).
require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log_error "Скрипт нужно запустить под root (sudo)"
    return 1
  fi
}

# idempotent "описание" "test cmd" "do cmd"
#   Если test cmd возвращает 0 → log_skip и выход.
#   Иначе → log_do, выполнить do cmd. Если do cmd упал → log_error и return 1.
# Используется для одношаговых операций.
idempotent() {
  local desc="$1"
  local test_cmd="$2"
  local do_cmd="$3"

  if eval "$test_cmd" >/dev/null 2>&1; then
    log_skip "$desc"
    return 0
  fi

  log_do "$desc"
  if ! eval "$do_cmd"; then
    log_error "$desc — команда упала: $do_cmd"
    return 1
  fi
  return 0
}

# check_step "name" "test command"  - для cluster-health.sh.
# Печатает [OK] / [FAIL]; глобально инкрементит __FAIL_COUNT для итогового exit-кода.
check_step() {
  local name="$1"
  local test_cmd="$2"
  if eval "$test_cmd" >/dev/null 2>&1; then
    log_ok "$name"
    return 0
  else
    __FAIL_COUNT=$((__FAIL_COUNT + 1))
    log_error "$name"
    return 1
  fi
}

# check_step_with_output "name" "test command"
#   То же, но при провале повторяет команду и печатает её stdout/stderr для диагностики.
check_step_with_output() {
  local name="$1"
  local test_cmd="$2"
  local out
  if out=$(eval "$test_cmd" 2>&1); then
    log_ok "$name"
    return 0
  else
    __FAIL_COUNT=$((__FAIL_COUNT + 1))
    log_error "$name"
    printf '%s%s%s\n' "$C_DIM" "$out" "$C_RESET" | sed 's/^/        /'
    return 1
  fi
}

# wait_for "описание" "test command" max_seconds [interval_seconds]
#   Поллит test command, пока не вернёт 0 или не выйдет таймаут.
wait_for() {
  local desc="$1"
  local test_cmd="$2"
  local max_sec="${3:-180}"
  local interval="${4:-3}"
  local elapsed=0

  log_info "Ожидание: $desc (timeout ${max_sec}s)"
  while [ "$elapsed" -lt "$max_sec" ]; do
    if eval "$test_cmd" >/dev/null 2>&1; then
      log_ok "$desc"
      return 0
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
  log_error "$desc — timeout ${max_sec}s"
  return 1
}

# print_summary - финальный счётчик. Возвращает 0 если __FAIL_COUNT == 0.
print_summary() {
  log_section "Итог"
  printf '  %s[SKIP]%s  %d\n' "$C_DIM" "$C_RESET" "$__SKIP_COUNT"
  printf '  %s[DO]%s    %d\n' "$C_YELLOW" "$C_RESET" "$__DO_COUNT"
  if [ "$__FAIL_COUNT" -gt 0 ]; then
    printf '  %s[FAIL]%s  %d\n' "$C_RED" "$C_RESET" "$__FAIL_COUNT"
    return 1
  fi
  printf '  %s[FAIL]%s  0\n' "$C_GREEN" "$C_RESET"
  return 0
}

# kubectl_or_microk8s - выбирает kubectl или microk8s kubectl. Используется в скриптах,
# которые работают и локально (есть kubectl с настроенным kubeconfig) и на master (microk8s).
KUBECTL="${KUBECTL:-}"
if [ -z "$KUBECTL" ]; then
  if command -v kubectl >/dev/null 2>&1; then
    KUBECTL="kubectl"
  elif command -v microk8s >/dev/null 2>&1; then
    KUBECTL="microk8s kubectl"
  fi
fi

# Дефолтный namespace платформы.
PLATFORM_NS="${PLATFORM_NS:-platform}"

# Имена нод по умолчанию (могут быть переопределены через ENV).
MASTER_NODE_NAME="${MASTER_NODE_NAME:-master}"
GPU_NODE_NAME="${GPU_NODE_NAME:-gpu-worker}"
GPU_NODE_LABEL_KEY="${GPU_NODE_LABEL_KEY:-accelerator}"
GPU_NODE_LABEL_VALUE="${GPU_NODE_LABEL_VALUE:-nvidia-gpu}"

# IP-адреса (для join, миграции из compose). Можно переопределить ENV.
MASTER_HOST_IP="${MASTER_HOST_IP:-84.38.184.105}"
GPU_HOST_IP="${GPU_HOST_IP:-188.246.224.228}"
SSH_USER="${SSH_USER:-root}"

# disable_host_firewall - идемпотентно отключает UFW (host-level firewall).
# Канон 2026 для нод Kubernetes: трафик контролируется CNI NetworkPolicies
# и инфраструктурой outside (cloud-provider firewall / ingress); host UFW мешает
# контрольным плоскостям (kubelet 10250, apiserver 16443, dqlite 19001, calico vxlan)
# и его правила-исключения дублируют логику CNI. Если требуется host firewall —
# использовать nftables-конфиг провайдера, а не ufw поверх Calico.
disable_host_firewall() {
  if ! command -v ufw >/dev/null 2>&1; then
    log_skip "ufw не установлен"
    return 0
  fi
  if ufw status 2>/dev/null | head -1 | grep -q 'inactive'; then
    log_skip "ufw уже отключён"
    return 0
  fi
  log_do "ufw disable (host firewall → CNI NetworkPolicies)"
  ufw --force disable
}
