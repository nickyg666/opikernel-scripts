#!/usr/bin/env python3
"""PA 2026-09-21 01:2xZ: restore canonical queue headings.

Incident: agentic-pool/BACKLOG.md (mtime 09-21 01:13:53) lost all 24 `### BL-NN`
heading lines while keeping all 24 `status:` lines. Proof it is a PURE strip:
    diff <(grep -v '^### BL-' BACKLOG.md.lastgood) BACKLOG.md  ->  0 lines
so BACKLOG.md == lastgood minus headings (35661 - 34077 = 1584 B = 24 * 66 B).
Restoring lastgood is therefore lossless.
"""
import hashlib
import pathlib
import shutil
import time

POOL = pathlib.Path("/home/host/opikernel/agentic-pool")
LIVE = POOL / "BACKLOG.md"
LG = POOL / "BACKLOG.md.lastgood"
stamp = time.strftime("%Y%m%d-%H%M%S")


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def report(tag):
    t = LIVE.read_text(errors="replace")
    print(f"{tag} md5={md5(LIVE)} size={LIVE.stat().st_size} "
          f"headings={t.count(chr(10) + '### BL-')} "
          f"states={t.count(chr(10) + 'status:') + t.startswith('status:')} "
          f"fused={t.count(chr(10) + '### ###')}")


corpse = POOL / f"BACKLOG.md.headings-stripped-{stamp}"
shutil.copy2(LIVE, corpse)
lg_before = md5(LG)
report("before")
shutil.copy2(LG, LIVE)
report("after ")
print(f"corpse={corpse.name} lastgood_md5_before={lg_before} lastgood_md5_after={md5(LG)}")
