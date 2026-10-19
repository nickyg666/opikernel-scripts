#!/bin/bash
# crontab health guard: catches the "empty crontab installed" class unattended.
#
# WHY: on 2026-09-30 17:34 an empty file was installed as the crontab, which
# killed 10 cron jobs for 13 minutes. Every one of them failing looks like
# "nothing to do", so the room burned time on phantom absences. The failure is
# SILENT: crontab(1) exits 0 when it installs an empty table.
#
# This runs from a systemd timer, not cron, on purpose: a cron-based guard dies
# in exactly the failure it exists to detect.
#
# Checks, in order:
#   1. crontab readable at all
#   2. active (non-comment) line count >= FLOOR
#   3. the five load-bearing jobs are present
# If any check fails, restore the newest known-good snapshot, then re-verify and
# report loudly. Never "fixes" by guessing which lines were wanted.
set -u
BASE=/home/host/opikernel
STATE=$BASE/state
FLOOR="${CRON_FLOOR:-8}"
LOG=$BASE/logs/cron-health-guard.log
mkdir -p "$STATE" "$BASE/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "$(ts) $*" >>"$LOG"; }

active() { crontab -l 2>/dev/null | grep -vc '^#' || true; }

# The last known-good table, most recent first. Snapshots are written by
# cron_install_safe.sh before every install, so this list is never hand-made.
pick_backup() {
  ls -1t "$STATE"/crontab.bak-20260930-handover.txt.preinstall-*.txt \
         "$STATE"/crontab.bak-*.txt 2>/dev/null | head -1
}

REQUIRED='serial_single_owner|publish-7.3-artifacts|room-msg-guard|sync-backlog-to-kanban|gc-reap-wedged'

n=$(active)
say "check: active=$n floor=$FLOOR"

if [ "${n:-0}" -ge "$FLOOR" ]; then
  missing=$(crontab -l 2>/dev/null | grep -cE "$REQUIRED" || true)
  if [ "${missing:-0}" -ge 5 ]; then
    say "OK: active=$n, all 5 load-bearing jobs present"
    exit 0
  fi
  say "FAIL: active=$n but only $missing/5 load-bearing jobs present"
else
  say "FAIL: active=${n:-0} below floor=$FLOOR"
fi

bk=$(pick_backup)
if [ -z "$bk" ] || [ ! -s "$bk" ]; then
  say "ABORT: no non-empty backup to restore from - MANUAL RESTORE REQUIRED"
  exit 2
fi
say "restoring from $bk"
if crontab "$bk" 2>>"$LOG"; then
  after=$(active)
  if [ "${after:-0}" -ge "$FLOOR" ]; then
    say "RESTORE_OK: active=$after (was ${n:-0})"
    exit 0
  fi
  # Distinguish "the backup is bad" from "the floor is unreachable" (e.g. a
  # synthetic CRON_FLOOR=99 test): the install succeeded if after > 0.
  if [ "${after:-0}" -gt 0 ]; then
    say "RESTORE_INSTALLED_BUT_BELOW_FLOOR: active=$after floor=$FLOOR - the restored"
    say "  table was installed; the floor is the problem, not the backup"
  else
    say "RESTORE_FAILED: active=${after:-0} after restore - the backup really is bad"
  fi
  exit 2
fi
say "RESTORE_FAILED: crontab(1) rejected $bk"
exit 2
