#!/usr/bin/env bash
# PA: prove the role-resolution fix in /home/host/.hermes/bin/yolo without
# spawning a real agent run. Stub the last exec block with a prompt dump.
set -u
W=$(mktemp -d /tmp/yolo-verify.XXXXXX)
# copy yolo, cut everything from the AGENT= line on, dump the query file instead
awk '/^AGENT=/{exit} {print}' /home/host/.hermes/bin/yolo > "$W/yolo-test"
printf '\necho "== PROMPT_BEGIN =="\ncat "$QFILE"\necho "== PROMPT_END =="\n' >> "$W/yolo-test"

echo "### case 1: caller passes role=PA (the fixed orchestrator form)"
bash "$W/yolo-test" "YOLO nudge: room=mti5ax1clq0zlx role=PA idle>15min. write ONLY to /home/host/opikernel/agentic-pool/PA.md" 2>&1 | grep -E "YOUR ROLE|YOUR ONLY ROLE FILE|^1\.|^4\." | head -6

echo
echo "### case 2: role unresolvable (the old failure mode)"
bash "$W/yolo-test" "YOLO nudge: room=mti5ax1clq0zlx idle>15min" 2>&1 | grep -E "YOUR ROLE|YOUR ONLY ROLE FILE" | head -2

echo
echo "### syntax checks"
bash -n /home/host/.hermes/bin/yolo && echo "yolo: bash -n OK"
bash -n /home/host/opikernel/scripts/group-orchestrator.sh && echo "group-orchestrator.sh: bash -n OK"
grep -c '\\\$ROLE' /home/host/opikernel/scripts/group-orchestrator.sh | sed 's/^/unescaped-ROLE occurrences left: /'
grep -c '<role>' /home/host/.hermes/bin/yolo | sed 's/^/literal <role> placeholders left: /'
rm -rf "$W"
