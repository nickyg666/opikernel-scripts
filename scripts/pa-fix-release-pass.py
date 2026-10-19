#!/usr/bin/env python3
"""PA tick 03:14 — fix two defects my 03:13 release pass introduced:
1) case bug: 'backlog-worker2' (lowercase b) vs roster 'Backlog-worker2' -> live KDG claims
   BL-03 (claimed) and BL-17 (done) were wrongly released. Restore both claims.
2) sync-backlog-to-kanban.py:93 copies claimed-by into the assignee column verbatim, so my
   placeholder text landed in the kanban assignee. Delete the claimed-by line on genuinely
   released items (open + no assignee is what makes them grabbable) and demote the note to a
   '#' comment the parsers ignore.
"""
import re, pathlib

P = pathlib.Path("/home/host/opikernel/agentic-pool/BACKLOG.md")
RESTORE = {"BL-03": ("claimed", "backlog-worker2"), "BL-17": ("done", "backlog-worker2")}
text = P.read_text()
blocks = re.split(r"(?m)^(?=### )", text)
fixed = []
for i, b in enumerate(blocks):
    m = re.search(r"(?m)^### (BL-\d+)", b)
    if not m:
        continue
    bid = m.group(1)
    if bid in RESTORE:
        st, who = RESTORE[bid]
        b2 = re.sub(r"(?m)^status: open[ \t]*$", f"status: {st}", b, count=1)
        b2 = re.sub(r"(?m)^claimed-by: \(none.*$", f"claimed-by: {who}", b2, count=1)
        b2 = re.sub(r"(?m)^released: .*$", "", b2)
        b2 = re.sub(r"\n{3,}", "\n\n", b2)
        blocks[i] = b2
        fixed.append(f"restored {bid} status={st} claimed-by={who}")
        continue
    if re.search(r"(?m)^claimed-by: \(none", b):
        b2 = re.sub(r"(?m)^claimed-by: \(none.*\n", "", b, count=1)
        b2 = re.sub(r"(?m)^released: ", "# released: ", b2, count=1)
        blocks[i] = b2
        fixed.append(f"released {bid}: claimed-by line removed, note demoted to comment")
P.write_text("".join(blocks))
print("\n".join(fixed))
