#!/bin/bash
# start-group-orchestrator.sh — scoped launcher/keepalive for the KERNEL group orchestrator.
#
# WHY (PA, 2026-09-20 18:5x): the daemon ran with ROOM_ID="" so it processed every room
# the detector returned, including the Neorunner room mti3yr2g3yjpyr — a different team's
# room with NO kernel agents. Worse, gc-post resolves "--as orchestrator" to the room's
# only member identity, so in mti3 every auto-nudge landed as senderType='member' (userName
# 'admin', authUserId 1 = the human). The detector's attendance gate ("a non-agent member
# posted within ROOM_HUMAN_MIN") therefore saw a fresh human post every ~66s, marked the
# room attended, and looped forever — the orchestrator was keeping its own target alive
# (108 such rows in 2h, 8,748 historically).
#
# FIX: ORCH_ROOMS is the detector's authoritative allowlist. The kernel orchestrator is
# scoped to the kernel room ONLY; Neorunner/mti3* is never processed by it.
#
# Usage:
#   start-group-orchestrator.sh            # launch if not already running
#   start-group-orchestrator.sh --ensure   # cron keepalive: silent no-op when alive
set -uo pipefail

ROOT=/home/host/opikernel
LOCK="$ROOT/state/group-orchestrator.lock"
LOG="$ROOT/logs/group-orchestrator.log"
ENSURE="${1:-}"

export ORCH_ROOMS="${ORCH_ROOMS:-mti5ax1clq0zlx}"   # kernel room only — never mti3*
export ROOM_ID=""                                   # empty => use detector's room set
export LOG

mkdir -p "$ROOT/logs" "$ROOT/state"
touch "$LOCK"

# The daemon holds an exclusive flock on fd 8 of $LOCK for its whole life.
# NOTE: the /etc/crontab */1 invoker runs the daemon as ROOT, so $LOCK can end up
# root-owned (0600) — a `flock -n "$LOCK"` test then fails to open it and reads as
# "lock held" even with no daemon running (false positive, seen 18:54). Detect the
# live process instead; the flock is still the daemon's own single-instance guard.
HOLDER=$(ps -eo pid,cmd | awk '/bash \/home\/host\/opikernel\/scripts\/group-orchestrator\.sh$/ {print $1}' | head -1)
if [ -n "$HOLDER" ]; then
  # A holder exists. Exit silently on the cron path; say so interactively.
  [ -n "$ENSURE" ] || echo "already running pid=$HOLDER"
  exit 0
fi
chown "$(id -un)" "$LOCK" 2>/dev/null || sudo -n chown "$(id -un)" "$LOCK" 2>/dev/null || true

setsid nohup bash "$ROOT/scripts/group-orchestrator.sh" >>"$LOG" 2>&1 &
sleep 1
NEWPID=$(pgrep -f "bash $ROOT/scripts/group-orchestrator.sh" | head -1)
# PA 2026-09-20 21:5x: the daemon's own `sleep 60` child INHERITS fd 8 (the flock) and survives a
# TERM of the parent (reparented to pid 1). The orphan then holds $LOCK forever, so every relaunch
# self-exits with "another orchestrator instance holds ..." and the room goes DARK while this
# launcher (and the keepalive cron) still report a successful launch. A holder that is provably
# NOT a daemon process is that orphan — reap it and launch once more.
if [ -z "$NEWPID" ]; then
  for hp in $(fuser "$LOCK" 2>/dev/null); do
    hc=$(tr '\0' ' ' < "/proc/$hp/cmdline" 2>/dev/null)
    case "$hc" in *group-orchestrator.sh*) continue ;; esac
    echo "reaping stale flock holder pid=$hp cmd='${hc:-?}'"
    kill "$hp" 2>/dev/null && sleep 1
  done
  setsid nohup bash "$ROOT/scripts/group-orchestrator.sh" >>"$LOG" 2>&1 &
  sleep 2
  NEWPID=$(pgrep -f "bash $ROOT/scripts/group-orchestrator.sh" | head -1)
fi
echo "launched group-orchestrator pid=${NEWPID:-?} ORCH_ROOMS=$ORCH_ROOMS"
