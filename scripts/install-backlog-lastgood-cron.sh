#!/usr/bin/env bash
# PA: install the canonical-queue last-good guard into crontab (idempotent).
set -euo pipefail
LINE='1-56/5 * * * * flock -n /tmp/backlog-lastgood.flock /usr/bin/python3 /home/host/opikernel/scripts/backlog-lastgood-guard.py --check >> /home/host/opikernel/logs/backlog-lastgood-guard.cron.log 2>&1'
TMP=$(mktemp)
crontab -l > "$TMP" 2>/dev/null || true
if grep -qF 'backlog-lastgood-guard.py' "$TMP"; then
  echo "already installed"
else
  printf '%s\n' "$LINE" >> "$TMP"
  # shellcheck source=/home/host/opikernel/scripts/cron-install-safe.sh
  source /home/host/opikernel/scripts/cron-install-safe.sh
  cron_install_safe "$TMP" 1 || { echo "ABORT: install refused"; exit 1; }
  echo "installed"
fi
rm -f "$TMP"
crontab -l | grep -c backlog-lastgood-guard
