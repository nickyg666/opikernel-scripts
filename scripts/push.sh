#!/bin/bash
# push.sh — reliably push a local file to a remote host (cat-pipe, no scp/curl).
# Usage: push.sh <local-file> <user@host>:<remote-path>
# Example: push.sh ./patch.py orangepi@192.168.0.151:/home/orangepi/pvrgl-work/patch.py
set -e
SRC="$1"
DST="$2"
if [ -z "$SRC" ] || [ -z "$DST" ]; then
  echo "usage: push.sh <local-file> <user@host>:<path>" >&2
  exit 2
fi
HOST="${DST%%:*}"
RPATH="${DST#*:}"
LMD5=$(md5sum "$SRC" | awk '{print $1}')
# Ensure the remote directory exists, then pipe the file through cat.
ssh -o ConnectTimeout=10 "$HOST" "mkdir -p $(dirname "$RPATH") && cat > '$RPATH'" < "$SRC"
RMD5=$(ssh -o ConnectTimeout=10 "$HOST" "md5sum '$RPATH'" | awk '{print $1}')
if [ "$LMD5" != "$RMD5" ]; then
  echo "PUSH FAILED: local=$LMD5 remote=$RMD5" >&2
  exit 1
fi
echo "PUSH OK $SRC -> $DST ($LMD5)"
