#!/bin/bash
# restore-hardware-crons.sh — put back the two hardware crons from the handover
# backup and re-enable them, undoing disable-hardware-crons.sh.
# Use when the next session wants automation restored.
set -u
BAK=/home/host/opikernel/state/crontab.bak-20260930-handover.txt
MARK="# HANDED-OVER "
PATTERNS=("board-lease-renew.sh" "card-state-poll.py")
[ -f "$BAK" ] || { echo "no backup at $BAK"; exit 1; }

TMP=$(mktemp)
crontab -l 2>/dev/null | sed "s|^${MARK}||" > "$TMP"

miss=0
for p in "${PATTERNS[@]}"; do
  line=$(grep -F "$p" "$BAK" | head -1)
  if [ -z "$line" ]; then
    echo "ERROR: $p not found in backup"; miss=1; continue
  fi
  if grep -qF "$p" "$TMP"; then
    echo "already active: $p"
  else
    printf '%s\n' "$line" >> "$TMP"
    echo "restored: $p"
  fi
done
[ $miss -eq 0 ] || { echo "ABORT: nothing installed"; rm -f "$TMP"; exit 1; }
# shellcheck source=/home/host/opikernel/scripts/cron-install-safe.sh
source /home/host/opikernel/scripts/cron-install-safe.sh
cron_install_safe "$TMP" "${CRON_MIN_ACTIVE:-8}" || { echo "ABORT: install refused, table untouched"; exit 1; }
rm -f "$TMP"
echo "=== active hardware crons now ==="
crontab -l 2>/dev/null | grep -E "board-lease-renew|card-state-poll"