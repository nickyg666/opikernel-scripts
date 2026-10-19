#!/usr/bin/env python3
"""Repair agentic-pool/BACKLOG.md after a markdown-ESCAPED repost appended an extra
`### ` prefix to the doc title and every `### BL-NN` item heading.

Detect:  `grep -c '^### BL-' BACKLOG.md` == 0 while `^### ### BL-` == 24.
Fix:     the second (complete, escaped) copy of the document is un-escaped in place
         and becomes the file; the stale clean head that precedes it is dropped.
Never runs without writing a dated backup first. Idempotent: exits 0 doing nothing
when the file is already clean.
"""
import hashlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

F = Path("/home/host/opikernel/agentic-pool/BACKLOG.md")
ESC = re.compile(r"^### (### BL-|# )")


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def lint(text: str) -> dict:
    lines = text.splitlines()
    items = [ln for ln in lines if re.match(r"^### BL-\d", ln)]
    states = {}
    for ln in lines:
        m = re.match(r"^status:\s*(\w+)", ln)
        if m:
            states[m.group(1)] = states.get(m.group(1), 0) + 1
    esc = sum(1 for ln in lines if ESC.match(ln))
    return {"items": len(items), "escaped": esc, "states": states, "lines": len(lines)}


raw = F.read_text()
before = lint(raw)
print(f"BEFORE {F.name}: md5={md5(F)} items={before['items']} escaped={before['escaped']} lines={before['lines']}")
print(f"BEFORE states: {before['states']}")
if before["escaped"] == 0:
    print("already clean — no action")
    sys.exit(0)
if before["items"]:
    print("headings already parse cleanly — refusing (would be a different corruption)")
    sys.exit(2)

lines = raw.splitlines(keepends=True)
# first escaped title line marks the start of the complete escaped copy
start = next(i for i, ln in enumerate(lines) if ESC.match(ln))
head = lines[:start]
region = lines[start:]
fixed = "".join(ESC.sub(lambda m: "### BL-" if m.group(1).startswith("###") else "# ", ln) for ln in region)

bak = F.with_name(f"{F.name}.bak-escape-{time.strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(F, bak)
print(f"backup -> {bak.name}")

F.write_text(fixed)
after = lint(fixed)
print(f"AFTER  {F.name}: md5={md5(F)} items={after['items']} escaped={after['escaped']} lines={after['lines']}")
print(f"AFTER states: {after['states']}")
print(f"head dropped ({len(head)} lines): {head[0].strip()!r} ... {head[-1].strip()!r}")

# content-preservation check: un-escaped region must contain every escaped line's payload
payload = [ESC.sub("", ln).rstrip() for ln in region]
missing = [p for p in payload if p and p not in fixed]
print(f"payload lines={len(payload)} missing_after_fix={len(missing)}")
if missing:
    print("MISSING SAMPLE:", missing[:3])
    sys.exit(3)

lintcmd = ["grep", "-c", "^### BL-", str(F)]
print("lint `grep -c '^### BL-'` =", subprocess.run(lintcmd, capture_output=True, text=True).stdout.strip())
