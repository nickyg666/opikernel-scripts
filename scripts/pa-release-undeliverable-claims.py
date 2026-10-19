#!/usr/bin/env python3
"""PA tick 03:13 — release BACKLOG claims held by agents that cannot be dispatched in
KernelDev-GPU (room mti5ax1clq0zlx). Same class as the BL-14 reassignment TelegramRunner
did at 04:31 UTC: claimed-by is the canonical assignee (sync-backlog-to-kanban.py:93), and a
claim held by an agent absent from this room's gc_room_agents roster is deliverable-nowhere.
Releasing => status: open => kstatus ready, no assignee => grabbable in this room.
"""
import re, time, pathlib

P = pathlib.Path("/home/host/opikernel/agentic-pool/BACKLOG.md")
KDG = {"Backlog-worker2", "PA", "TelegramRunner", "backlog-worker1", "build-engineer",
       "debugger", "gpu-driver-expert", "kconfig-auditor", "kernel-architect"}
text = P.read_text()
blocks = re.split(r"(?m)^(?=### )", text)
stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
changed = []
for i, b in enumerate(blocks):
    m = re.search(r"(?m)^### (BL-\d+)", b)
    if not m:
        continue
    cm = re.search(r"(?m)^claimed-by:[ \t]*(.+?)[ \t]*$", b)
    if not cm:
        continue
    who = cm.group(1).strip()
    if who in KDG:
        continue
    bid = m.group(1)
    nb = b.replace(cm.group(0), f"claimed-by: (none — {who} is absent from the KernelDev-GPU roster)")
    # also flip the status line of this block
    nb, n = re.subn(r"(?m)^status: claimed[ \t]*$", "status: open", nb, count=1)
    nb, n2 = re.subn(r"(?m)^claimed-at:.*$",
                     f"released: {stamp} by PA — claim held by '{who}', not a member of room "
                     f"mti5ax1clq0zlx (gc_room_agents); released to open so a dispatchable agent can grab it",
                     nb, count=1)
    blocks[i] = nb
    changed.append((bid, who, n, n2))
P.write_text("".join(blocks))
for bid, who, n, n2 in changed:
    print(f"released {bid}: claimer '{who}' not in KDG roster -> status:open (status_flip={n}, note={n2})")
print(f"total released: {len(changed)}")
