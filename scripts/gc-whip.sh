#!/bin/bash
# gc-whip — system cron fire-and-forget for KernelDev-GPU room mti5ax1clq0zlx
# Purpose: auto-approve + keep everyone working. YOLO.
# Deliver: detached hermes chat (not systemd scope).
set -e
ROOM=mti5ax1clq0zlx
TOKEN=$(cat /home/host/.hermes/.token 2>/dev/null || echo "")
if [ -z "$TOKEN" ]; then
  TOKEN=$(cat ~/.hermes/.token 2>/dev/null || echo "")
fi
# No token? Just use CLI with --provider directly.
# Check if group is even still active (look up room)
QFILE=$(mktemp /tmp/gc-whip.XXXXXX.txt)
cat > "$QFILE" <<'Q'
YOLO — continue your next best step. No back-and-forth, just do ONE concrete thing on this task, write the result to the room, then stop. Keep the other agents moving.
Q
setsid nohup /home/host/.hermes/hermes-agent/venv/bin/hermes chat \
  --query-file "$QFILE" \
  --yolo \
  -m omni/freeAF --provider custom:neato \
  >> /home/host/.hermes/logs/gc-whip.log 2>&1 < /dev/null &
disown
rm -f "$QFILE"
exit 0
