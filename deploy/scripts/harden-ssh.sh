#!/usr/bin/env bash
# Pubkey-only SSH. Без ключа в authorized_keys падает — иначе lockout.
# Ubuntu 22.04+: Include sshd_config.d идёт первым; 00-*.conf перекрывает 50-cloud-init.conf.
# Запускать под root на ноде. Вызывается из bootstrap-master.sh.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

AUTH_KEYS="/root/.ssh/authorized_keys"
DROPIN="/etc/ssh/sshd_config.d/00-platform-hardening.conf"

log_section "SSH: только pubkey"

if [ ! -s "$AUTH_KEYS" ] || ! grep -qE '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-|sk-ssh-)' "$AUTH_KEYS"; then
  log_error "Нет pubkey в $AUTH_KEYS — отказ, чтобы не закрыть вход"
  exit 1
fi
log_ok "authorized_keys содержит ключ"

mkdir -p /etc/ssh/sshd_config.d

DROPIN_BODY=$(cat <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PermitEmptyPasswords no
AuthenticationMethods publickey
UseDNS no
LoginGraceTime 20
MaxStartups 30:50:100
MaxAuthTries 3
EOF
)

if [ -f "$DROPIN" ] && [ "$(cat "$DROPIN")" = "$DROPIN_BODY" ]; then
  log_skip "sshd drop-in уже применён ($DROPIN)"
else
  log_do "писать $DROPIN"
  printf '%s\n' "$DROPIN_BODY" > "$DROPIN"
  chmod 644 "$DROPIN"
fi

if ! sshd -t; then
  log_error "sshd -t не прошёл — drop-in не применяем"
  exit 1
fi

if systemctl reload ssh; then
  log_ok "systemctl reload ssh"
elif systemctl reload sshd; then
  log_ok "systemctl reload sshd"
else
  log_error "не удалось reload ssh/sshd"
  exit 1
fi

print_summary
exit 0
