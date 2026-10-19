#!/bin/bash
# disable-hardware-crons.sh — comment out (never delete) the cron jobs that touch
# board HARDWARE, so a handover session can take the board without fighting an
# automation loop. Restores the lines first if a previous pass removed them.
#
# BUG I SHIPPED FIRST (2026-09-30, own it): v1 ran
#     grep -v "$p" "$TMP" > "$TMP.2"; awk ... "$TMP.2" > "$TMP"
# so grep DELETED the line before awk could prefix it with "# HANDED-OVER ". Both
# hardware crons were removed from the crontab entirely. The verification grep
# then found nothing and the script printed an empty "hardware crons after" — which
# read like success. Recovered from state/crontab.bak-20260930-handover.txt.
# Lesson now enforced here: a disable step must FAIL LOUDLY when it finds nothing
# to disable, and must never delete.
#
# Why these two and not the others:
#   board-lease-renew  defaults to BOARD_LEASE_OWNER=TelegramRunner and, with no
#                      live lease, calls `board_lease.sh take` — so within 5 min of
#                      a handover releasing the lease it re-grabs it under that
#                      owner name. It cannot steal a live foreign lease, but it does
#                      re-create the one that was just given up.
#   card-state-poll    ssh's the tab and mounts/reads the SD reader. Read-only on
#                      the card, but it is the only automation reporting where
#                      hardware physically is, and the next session owns that.
#
# Read-only/local crons are LEFT RUNNING on purpose: publish-7.3-artifacts,
# room-guard, kanban-sync, omniroute-pool, ocfree-refresh, backlog-lastgood-guard,
# gc-reap. None touch the board, the plug, or the serial port.
#
# Idempotent, non-destructive: lines are only prefixed, never removed.
set -u
MARK="# HANDED-OVER "
BAK=/home/host/opikernel/state/crontab.bak-20260930-handover.txt
PATTERNS=("board-lease-renew.sh" "card-state-poll.py")
TMP=$(mktemp)
crontab -l 2>/dev/null | sed "s|^${MARK}||" > "$TMP" || true

# Restore from backup any pattern that is missing entirely (v1 may have deleted it).
for p in "${PATTERNS[@]}"; do
  if ! grep -qF "$p" "$TMP" && [ -f "$BAK" ]; then
    line=$(grep -F "$p" "$BAK" | head -1)
    [ -n "$line" ] && printf '%s\n' "$line" >> "$TMP"
  fi
done

# Prefix the hardware lines so they no longer execute.
for p in "${PATTERNS[@]}"; do
  awk -v pat="$p" -v mark="$MARK" '
    index($0, pat) { print mark $0; next }
    { print }
  ' "$TMP" > "$TMP.new"
  mv "$TMP.new" "$TMP"
done

# VERIFY, loudly. A silent pass here is exactly how v1 looked like a success.
miss=0
for p in "${PATTERNS[@]}"; do
  line=$(grep -F "$p" "$TMP" | head -1)
  case "$line" in
    "${MARK}"*) echo "DISABLED: $p" ;;
    *) echo "ERROR: $p is NOT disabled (found: ${line:-nothing})"; miss=1 ;;
  esac
done
[ $miss -eq 0 ] || { echo "ABORT: crontab NOT installed, leaving it untouched"; rm -f "$TMP" "$TMP.new"; exit 1; }

# shellcheck source=/home/host/opikernel/scripts/cron-install-safe.sh
source /home/host/opikernel/scripts/cron-install-safe.sh
cron_install_safe "$TMP" "${CRON_MIN_ACTIVE:-8}" || { echo "ABORT: install refused, table untouched"; exit 1; }
rm -f "$TMP" "$TMP.new"
echo "=== crontab installed; hardware crons now: ==="
crontab -l 2>/dev/null | grep -E "board-lease-renew|card-state-poll"
echo "=== active (non-commented) cron count ==="
crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | wc -l