#!/usr/bin/env python3
"""PA fix: group-orchestrator.sh:470 shipped a LITERAL \\$ROLE to the yolo agent.
Replace that one line so the role name is expanded at spawn time and the write
target is one exact path."""
import hashlib, pathlib, shutil, sys

P = pathlib.Path("/home/host/opikernel/scripts/group-orchestrator.sh")
BAK = P.with_suffix(".sh.bak-pa-line470-20260920-1632")
src = P.read_text()
lines = src.split("\n")
idx = 469  # 0-based -> line 470
old = lines[idx]
NEW = (
    '          ROLE="$role" setsid /home/host/.hermes/bin/yolo '
    '"YOLO nudge: room=$ROOM role=$role idle>15min. Do ONE concrete next step for $ROOM. '
    'Read your role\'s last message, then write ONLY to '
    '/home/host/opikernel/agentic-pool/$role.md (that exact path; create no other file). '
    'Post progress with: gc-post --room $ROOM --as $role. '
    'NO @all spam, no asking Nick. Max 3 tool calls, max 4000 words." '
    "</dev/null >/dev/null 2>&1 8>&- &"
)
if "role=\\$ROLE" not in old and "$ROLE" not in old:
    print("ABORT: line 470 does not contain the escaped placeholder — refusing to edit")
    print("line470:", old[:160])
    sys.exit(2)
shutil.copy2(P, BAK)
lines[idx] = NEW
P.write_text("\n".join(lines))
print("backup     :", BAK.name, hashlib.md5(BAK.read_bytes()).hexdigest()[:8])
print("new 470    :", P.read_text().split("\n")[469][:150])
print("md5 now    :", hashlib.md5(P.read_bytes()).hexdigest()[:8])
print("escapes left in file:", P.read_text().count("\\$ROLE"))
