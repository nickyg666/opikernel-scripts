#!/usr/bin/env python3
"""PA tick 04:50 EDT (08:50Z) — repair the canonical queue.

Symptom: agentic-pool/BACKLOG.md (14,048 B, 04:28:22) has ZERO `### BL-NN` sections and
ZERO `claimed-by:` lines (search_files counts, this turn): it was overwritten by a lossy
digest, so `scripts/backlog-section-lint.py` dies with IndexError (items/ids empty) and
`scripts/sync-backlog-to-kanban.py` performs 0 operations -> the board is frozen and no
agent can claim anything.

Fix: rebuild from the last well-formed snapshot (BACKLOG.md.bak20260920-0300, 16,098 B,
19 sections / 13 claimed-by) and re-apply every post-03:00 state change that the digest
recorded, so no release/reassignment is lost. Digest is preserved verbatim
(BACKLOG.md.digest-20260920-0450.bak). Idempotent: re-running on a rebuilt file is a no-op.
"""
import hashlib
import pathlib
import re
import shutil
import time

POOL = pathlib.Path("/home/host/opikernel/agentic-pool")
P = POOL / "BACKLOG.md"
BASE = POOL / "BACKLOG.md.bak20260920-0300"
DIGEST_BAK = POOL / "BACKLOG.md.digest-20260920-0450.bak"
stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

# LIVE room mti5ax1clq0zlx roster, read this turn from gc_room_agents (hermes-web-ui.db):
# kernel-architect, gpu-driver-expert, build-engineer, debugger, kconfig-auditor,
# TelegramRunner, default, backlog-worker1, Backlog-worker2, PA
NON_ROSTER = ("minecraft", "minecraftplayer", "Neo", "network-architect",
              "network architect", "py-specialist", "py specialist", "workflow-organizer",
              "Workflow organizer")

# (status, claimed-by, note) — None claimed-by => release to open
OVERRIDES = {
    "BL-01": ("claimed", "backlog-worker1", None),
    # BL-02 held 'minecraft' (dead id, AGENTS.md) then workflow-organizer (non-roster)
    "BL-02": ("open", None, "released %s by PA — claim held by 'minecraft'/'workflow-organizer', "
                            "neither dispatchable in room mti5ax1clq0zlx" % stamp),
    "BL-03": ("claimed", "backlog-worker2", None),
    # BL-04 was network-architect (non-roster); board row now holds kconfig-auditor (in-room)
    "BL-04": ("claimed", "kconfig-auditor",
              "reassigned %s by PA — was network-architect (not in room mti5ax1clq0zlx); "
              "board row t_779c51cb already assigns kconfig-auditor" % stamp),
    # BL-05 was py-specialist (non-roster); board row now holds backlog-worker1 (in-room)
    "BL-05": ("claimed", "backlog-worker1",
              "reassigned %s by PA — was py-specialist (not in room mti5ax1clq0zlx); "
              "board row t_46e1ad5b already assigns backlog-worker1" % stamp),
    "BL-06": ("open", None, "released %s by PA — claim held by workflow-organizer, "
                            "not a member of room mti5ax1clq0zlx" % stamp),
    "BL-09": ("blocked", "PA", None),
    # TelegramRunner reassigned BL-14 at 04:31 UTC (verified in the digest)
    "BL-14": ("claimed", "kernel-architect",
              "reassigned 2026-09-20 04:31 UTC by TelegramRunner — was 'Neo' (Neorunner-only)"),
    # PA applied the boot.scr write to the staging card; only the boot gate is open
    "BL-16": ("claimed", "PA", None),
    "BL-19": ("claimed", "kernel-architect",
              "adjudicated %s by PA — earliest well-formed hold (kernel-architect, in-room); "
              "Backlog-worker2's duplicate claim dropped. Board row t_fab3a35d reads "
              "network-architect (non-roster) until the next sync run." % stamp),
}


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def rebuild(block, bid):
    status, who, note = OVERRIDES.get(bid, (None, None, None))
    if status is None:
        return block, None
    out, n_status = re.subn(r"(?m)^status:.*$", "status: %s" % status, block, count=1)
    if n_status == 0:
        return block, None
    if who is not None:
        out, n_who = re.subn(r"(?m)^claimed-by:.*$", "claimed-by: %s" % who, out, count=1)
        if n_who == 0:
            out = re.sub(r"(?m)^(status:.*)$", r"\1\nclaimed-by: %s" % who, out, count=1)
    else:
        out, n_who = re.subn(r"(?m)^claimed-by:.*$",
                             "# claimed-by: (none — released to open)", out, count=1)
    if note:
        out = re.sub(r"(?m)^(status:.*)$", r"\1\n# %s" % note, out, count=1)
    return out, (bid, status, who or "-", n_who)


def main():
    if not BASE.exists():
        raise SystemExit("base snapshot missing: %s" % BASE)
    if not DIGEST_BAK.exists():
        shutil.copy2(P, DIGEST_BAK)
    base = BASE.read_text()
    blocks = re.split(r"(?m)^(?=### )", base)
    report = []
    for i, b in enumerate(blocks):
        m = re.search(r"(?m)^### (BL-\d+)", b)
        if not m:
            continue
        nb, changed = rebuild(b, m.group(1))
        blocks[i] = nb
        if changed:
            report.append(changed)
    # preserve the digest's unique commentary verbatim, as comments, so no finding is lost
    digest_tail = ["\n\n---\n\n## PA digest preservation (comments only — no items)\n",
                   "# The 04:28:22 BACKLOG.md digest that lost the section structure is kept\n",
                   "# verbatim at agentic-pool/BACKLOG.md.digest-20260920-0450.bak (md5 %s).\n"
                   % md5(DIGEST_BAK)]
    text = "".join(blocks) + "".join(digest_tail)
    P.write_text(text)
    print("base=%s md5=%s bytes=%s" % (BASE.name, md5(BASE), BASE.stat().st_size))
    print("digest backup=%s md5=%s" % (DIGEST_BAK.name, md5(DIGEST_BAK)))
    for bid, status, who, n in sorted(report):
        print("  %-6s -> status=%-8s claimed-by=%-18s (claimed-by_lines=%d)" % (bid, status, who, n))
    print("rebuilt=%s md5=%s bytes=%s" % (P.name, md5(P), P.stat().st_size))


main()
