#!/usr/bin/env python3
"""Forward-scan classifier for agentic-pool/BACKLOG.md.

Every reader in the room (PA's sync, kanban import, agents grepping for work)
scans the file top-down and inherits the most recent '## ' section heading.
An OPEN item sitting under '## Done' is therefore silently classified done.

Usage: python3 scripts/backlog-section-lint.py [path]
Exit 0 = clean, 1 = defect found. Prints one line per defect.
"""
import re
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else
            "/home/host/opikernel/agentic-pool/BACKLOG.md")
lines = path.read_text().splitlines()

sections, cur, items, defects = [], None, [], []
for n, ln in enumerate(lines, 1):
    m = re.match(r"^##\s+(.*)$", ln)
    if m and not ln.startswith("###"):
        cur = m.group(1).strip()
        sections.append((n, cur))
        continue
    m = re.match(r"^###\s+(BL-\d+)\b(.*)$", ln)
    if m:
        items.append({"id": m.group(1), "line": n, "section": cur,
                      "title": m.group(2).strip(" :"), "status": None,
                      "claims": None, "status_lines": 0, "claimed_by": None,
                      "claimed_at_lines": 0})
        continue
    if items:
        it = items[-1]
        if ln.startswith("status:"):
            it["status_lines"] += 1
            if it["status"] is None:
                it["status"] = ln.split("status:", 1)[1].strip()
        elif ln.startswith("claimed-by:"):
            it["claimed_by"] = ln.split(":", 1)[1].strip()
        elif ln.startswith("claimed-at:"):
            it["claimed_at_lines"] += 1

ids = [i["id"] for i in items]
for it in items:
    sec = (it["section"] or "").lower()
    if it["status"] in ("open", "claimed", "ready", "in_progress") and "done" in sec:
        defects.append(f"{it['id']} line {it['line']}: status={it['status']} but section='{it['section']}'")
    if it["status_lines"] != 1:
        defects.append(f"{it['id']} line {it['line']}: {it['status_lines']} status: lines (want 1)")
    if it["status"] == "claimed" and not it["claimed_by"]:
        defects.append(f"{it['id']} line {it['line']}: claimed with no claimed-by:")
    if it["status"] in ("open", "ready") and it["claimed_by"]:
        defects.append(f"{it['id']} line {it['line']}: status={it['status']} but claimed-by={it['claimed_by']}")
    if it["claimed_at_lines"] > 1:
        defects.append(f"{it['id']} line {it['line']}: {it['claimed_at_lines']} uncommented claimed-at: lines "
                       f"(want <=1) — a released claim's timestamp left live; staleness/kanban readers take it as the current claim")
dupes = {i for i in ids if ids.count(i) > 1}
for d in sorted(dupes):
    defects.append(f"{d}: duplicate id")

print(f"file={path} md5={__import__('hashlib').md5(path.read_bytes()).hexdigest()} "
      f"bytes={path.stat().st_size}")
print(f"sections={[s[1] for s in sections]} items={len(items)} ids={ids[0]}..{ids[-1]}")
from collections import Counter
print("status:", dict(Counter(i["status"] for i in items)))
for d in defects:
    print("DEFECT:", d)
print("RESULT:", "CLEAN" if not defects else f"{len(defects)} defect(s)")
sys.exit(1 if defects else 0)
