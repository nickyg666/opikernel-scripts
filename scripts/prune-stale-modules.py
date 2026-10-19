#!/usr/bin/env python3
"""Delete stale /usr/lib/modules trees on a mounted card, keeping exactly one.

Why this exists: the 32G card carried TEN module trees. Two of them were
`7.3.0-rc2-00018-*` from DIFFERENT commits:
    7.3.0-rc2-00018-g7dc769e5fbd0-dirty   <- correct, holds the fixed modules
    7.3.0-rc2-00018-g8700775a95c3-dirty   <- stale, got loaded instead

modprobe picked whichever the search found first, so the board ran an old
driver while the fix sat unused on the card. Only the KEEP tree survives.

Safety: never deletes the tree named by KEEP, never deletes modules.dep of a
kept tree, prints sizes, and `sync` is the caller's job (the caller must sync
before pulling the card).
"""
import os
import shutil
import subprocess
import sys

CARD = sys.argv[1] if len(sys.argv) > 1 else "/mnt/usbsd"
KEEP = sys.argv[2] if len(sys.argv) > 2 else "7.3.0-rc2-00018-g7dc769e5fbd0-dirty"
# 6.18.19+ is the retired tree; keep it only if asked.
MODS = ["usr/lib/modules", "lib/modules"]


def du(p):
    r = subprocess.run(["du", "-sm", p], capture_output=True, text=True)
    try:
        return r.stdout.split()[0]
    except Exception:
        return "?"


def main():
    total_before = total_after = 0
    removed = []
    for base in MODS:
        root = os.path.join(CARD, base)
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name)
            if not os.path.isdir(p):
                continue
            sz = du(p)
            if name == KEEP:
                print("KEEP  %-46s %s MB" % (base + "/" + name, sz))
                total_after += int(sz) if sz.isdigit() else 0
                continue
            print("RM    %-46s %s MB" % (base + "/" + name, sz))
            shutil.rmtree(p, ignore_errors=True)
            removed.append(base + "/" + name)
        total_before += 0
    print("\nremoved %d stale trees" % len(removed))
    for r in removed:
        print("   - %s" % r)
    print("\nremaining:")
    for base in MODS:
        root = os.path.join(CARD, base)
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                print("   %s/%s" % (base, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())