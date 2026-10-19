#!/usr/bin/env bash
set -u
cd /home/host/opikernel
echo "== who names a file 'error_<room>.md' / 'unknown_role*' =="
grep -rn "unknown_role\|error_\${\|error_%s\|'error_'" scripts/ /home/host/.hermes/bin/ 2>/dev/null | grep -v '\.bak' | head -20
echo
echo "== live group-orchestrator.sh: any write into agentic-pool =="
grep -nE 'agentic-pool' scripts/group-orchestrator.sh | grep -nE '>|tee|cp |mv ' | head -20
echo
echo "== gc-post tool: does it write files? =="
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/.hermes/bin/gc-post 2>/dev/null
grep -nE 'agentic-pool|open\(|write' /home/host/.hermes/bin/gc-post 2>/dev/null | head -20
echo
echo "== the tiny files' contents (one line each, truncated) =="
for f in minecraft-player.md error_mti5ax1clq0zlx.md unknown_role_for_room_mti5ax1clq0zlx.md unknown.md mti3yr2g3yjpyr.md error.md; do
  p="agentic-pool/$f"
  if [ -f "$p" ]; then printf '%-46s %6s B  ' "$f" "$(stat -c%s "$p")"; head -c 90 "$p" | tr '\n' '|'; echo; fi
done
