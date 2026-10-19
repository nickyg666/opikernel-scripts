#!/usr/bin/env bash
# PA: audit LIVE claims in the canonical queue (agentic-pool/BACKLOG.md).
# Flags untimed claims (un-auditable) and claims older than AGE_LIMIT_H hours.
# Read-only. No writes to BACKLOG.md.
set -uo pipefail
B="${1:-/home/host/opikernel/agentic-pool/BACKLOG.md}"
AGE_LIMIT_H="${AGE_LIMIT_H:-24}"
now=$(date -u +%s)
awk -v now="$now" -v lim="$AGE_LIMIT_H" '
  /^### BL-/ { id=$2; c=0; by=""; ts=""; next }
  /^status:/ { if ($2=="claimed") c=1; else c=0; next }
  /^claimed-by:/ { by=$2; next }
  /^claimed-at:/ {
    if (!c) next
    ts=$2" "$3
    if (ts !~ /^20[0-9][0-9]-/) { printf "UNTIMED %-6s %-18s (no parseable claimed-at)\n", id, by; c=0; next }
    cmd="date -u -d \""ts"\" +%s"; cmd | getline e; close(cmd)
    age=int((now-e)/3600)
    flag=(age>=lim) ? "STALE" : "ok"
    printf "%-7s %-6s %-18s age=%3dh claimed=%s\n", flag, id, by, age, ts
    c=0
  }
' "$B" | sort -r
