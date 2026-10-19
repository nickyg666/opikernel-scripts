#!/usr/bin/env python3
"""PA: kill the prose that poisons loose `grep -c 'status: <state>'` probes.

The 12:52 orphan-stanza fix inserted header prose containing literal state-line
strings (`status: open`, `status: claimed`, ...). Anchored probes stay correct but the
loose probes workers actually run over-count (open=1, claimed=14 vs real 0/13).
Rewording prose so no line contains the literal 'status: <state>' string.
"""
import hashlib, re, shutil, sys, time

P = "/home/host/opikernel/agentic-pool/BACKLOG.md"
src = open(P, encoding="utf-8").read()
orig = src

subs = [
 ("1. Pick ONE item from a `## Open` section that is `status: open` and nobody else holds.",
  "1. Pick ONE item from a `## Open` section whose state line reads `status:` + `open`,\n   and that nobody else holds."),
 ("2. Edit the item in place: `status: claimed` + `claimed-by: <your role>` + `claimed-at: <UTC>`.",
  "2. Edit the item in place: set its state line to `claimed`, and add\n   `claimed-by: <your role>` + `claimed-at: <UTC>`."),
 ("4. On completion, set `status: done` + append one line `evidence: <command> -> <result>`.",
  "4. On completion, set the state line to `done` and append one line\n   `evidence: <command> -> <result>`."),
 ("5. Blocked? `status: blocked` + `blocker: <one line>`. Do NOT retry-spin.",
  "5. Blocked? set the state line to `blocked` and add `blocker: <one line>`. Do NOT retry-spin."),
 ("   invisible to the lint and inflates every naive `grep -c '^status: …'` probe (found 2026-09-20 12:52,",
  "   invisible to the lint and inflates every naive `grep -c '^status: …'` probe (found 2026-09-20 12:52,"),
]
for old, new in subs:
    if old not in src:
        print("MISS:", old[:60]); sys.exit(1)
    src = src.replace(old, new, 1)

# guard: no prose line may contain the literal status:<state> string outside a `### BL-` block
bad = [l for l in src.splitlines() if re.search(r"status:\s*(open|claimed|blocked|done)\b", l) and not l.strip().startswith("status:")]
if bad:
    print("REFUSING — would still poison probes:"); [print(" ", b) for b in bad]; sys.exit(1)

shutil.copy2(P, P + ".bak-proseprobe-" + time.strftime("%Y%m%d-%H%M%S"))
open(P, "w", encoding="utf-8").write(src)
print("bytes", len(orig), "->", len(src))
print("md5", hashlib.md5(src.encode()).hexdigest())
