#!/bin/bash
# agent-drift-guard.sh — cron wrapper (* * * * *), flock-guarded, zero inference.
#
# Stops agents that loop on the same output and restarts them on a fresh session:
#   scripts/agent-drift-guard.py --apply
# See that file's docstring for the detection signals and the stop/restart path.
#
# Manual runs for verification:
#   scripts/agent-drift-guard.sh --explain --no-dispatch   # detect + per-agent signal summary (no action)
#   scripts/agent-drift-guard.sh --self-test               # self-test
set -u
exec 9>/home/host/opikernel/scripts/agent-drift-guard.lock
if ! flock -n 9; then
    exit 0
fi
# MUST use the hermes venv python: gc-post.py (invoked with sys.executable) needs
# `socketio`, which /usr/bin/python3 does NOT have. Under /usr/bin/python3 every
# restart post fails with "[gc-post] SOCKET/POST FAILED: No module named 'socketio'"
# so the drifted agent is stopped but never re-dispatched.
HERMES_PY=/home/host/.hermes/hermes-agent/venv/bin/python3
if [ ! -x "$HERMES_PY" ]; then
    echo "drift-guard: FATAL $HERMES_PY missing — restart posts would fail" >&2
    exit 1
fi
exec "$HERMES_PY" /home/host/opikernel/scripts/agent-drift-guard.py --apply "$@"
