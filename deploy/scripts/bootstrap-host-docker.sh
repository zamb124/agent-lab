#!/usr/bin/env bash
# Docker Engine рядом с MicroK8s: свой dockerd и сокет /var/run/docker.sock.
# Snap docker и docker.io из Ubuntu не ставим: snap containerd — это MicroK8s,
# а ферма guest_runtime монтирует host sock (Helm type: Socket).
# Пакет containerd.io из Docker CE — /usr/bin/containerd, не snap microk8s.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

log_section "Host Docker Engine (guest_runtime sock)"

if snap list docker >/dev/null 2>&1; then
  log_error "установлен snap docker — снимите: snap remove docker. Нужен Docker CE, не snap."
  exit 1
fi

if docker info >/dev/null 2>&1 && [ -S /var/run/docker.sock ]; then
  log_skip "Docker Engine отвечает на /var/run/docker.sock"
  docker info --format '{{.ServerVersion}} {{.Driver}}'
  print_summary
  exit 0
fi

. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
  log_error "Docker CE repo рассчитан на Ubuntu, ID=${ID:-empty}"
  exit 1
fi

CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
if [ -z "$CODENAME" ]; then
  log_error "не удалось определить VERSION_CODENAME для Docker apt repo"
  exit 1
fi

ARCH="$(dpkg --print-architecture)"
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  log_do "Docker apt GPG"
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
else
  log_skip "Docker apt GPG"
fi

DOCKER_LIST=/etc/apt/sources.list.d/docker.list
EXPECTED_LINE="deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable"
if [ -f "$DOCKER_LIST" ] && grep -Fqx "$EXPECTED_LINE" "$DOCKER_LIST"; then
  log_skip "Docker apt repo"
else
  log_do "Docker apt repo"
  printf '%s\n' "$EXPECTED_LINE" > "$DOCKER_LIST"
fi

if dpkg -l 2>/dev/null | grep -qE '^ii[[:space:]]+docker-ce[[:space:]]'; then
  log_skip "пакет docker-ce"
else
  log_do "apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin"
  apt-get update -qq
  if ! DEBIAN_FRONTEND=noninteractive apt-get install -y \
    -o Dpkg::Options::="--force-confold" \
    -o Dpkg::Options::="--force-confdef" \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin; then
    log_error "apt-get install docker-ce failed"
    exit 1
  fi
fi

log_do "systemctl enable --now docker"
systemctl enable --now docker

if id ubuntu >/dev/null 2>&1; then
  idempotent \
    "пользователь ubuntu в группе docker" \
    "id -nG ubuntu | grep -qw docker" \
    "usermod -a -G docker ubuntu"
fi

if [ ! -S /var/run/docker.sock ]; then
  log_error "/var/run/docker.sock не появился после старта docker"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  log_error "docker info не отвечает после установки Docker Engine"
  journalctl -u docker --no-pager -n 40 || true
  exit 1
fi

log_ok "Docker Engine: $(docker info --format '{{.ServerVersion}}')"
print_summary
