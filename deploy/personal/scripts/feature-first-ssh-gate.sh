#!/usr/bin/env bash
# Install as root-owned /usr/local/libexec/smartploy-feature-first-ssh-gate
# with a dedicated restricted SSH key using authorized_keys:
# restrict,command="/usr/local/libexec/smartploy-feature-first-ssh-gate" ssh-ed25519 ...
# SSH_ORIGINAL_COMMAND comes from sshd; never evaluate or execute it.
set -Eeuo pipefail
umask 077
ORIGINAL="${SSH_ORIGINAL_COMMAND:-}"
if [[ ! "$ORIGINAL" =~ ^feature-first-deploy\ ([0-9a-f]{40})$ ]]; then
  echo "FEATURE_FIRST_DENIED: only an immutable SHA deploy command is allowed" >&2
  exit 41
fi
SHA="${BASH_REMATCH[1]}"
# Sudoers must grant only THIS executable, not sudo bash, sudo -i, Docker or Git:
# smartploy-cd ALL=(root) NOPASSWD: /usr/local/sbin/smartploy-feature-first-dispatch *
exec sudo -n /usr/local/sbin/smartploy-feature-first-dispatch "$SHA"
