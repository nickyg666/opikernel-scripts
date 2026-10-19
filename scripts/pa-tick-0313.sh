#!/usr/bin/env bash
# PA tick 03:13 — cross-room claim leak: which BACKLOG claims are undeliverable in KDG
set -u
B=/home/host/opikernel/agentic-pool/BACKLOG.md
DB=$HOME/.hermes-web-ui/hermes-web-ui.db
echo "== claimed items with their claimer string (awk by heading) =="
awk '/^### /{h=$0} /claimed-by:/{sub(/^[ \t]*claimed-by:[ \t]*/,""); print h" => "$0}' "$B"
echo "== KDG roster (room mti5ax1clq0zlx) =="
sqlite3 -readonly "$DB" ".timeout 8000" "select name,agentId,removedAt from gc_room_agents where roomId='mti5ax1clq0zlx' order by name;" 2>&1
echo "== Neorunner roster (room mti3yr2g3yjpyr) =="
sqlite3 -readonly "$DB" ".timeout 8000" "select name,agentId from gc_room_agents where roomId='mti3yr2g3yjpyr' order by name;" 2>&1
echo "== open/claimable count =="
grep -c '^### ' "$B"; grep -c 'status: open' "$B"; grep -c 'status: claimed' "$B"; grep -c 'status: blocked' "$B"
