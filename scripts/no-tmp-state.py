#!/usr/bin/env python3
"""Fail if any project tooling persists state under /tmp.

Why this exists
---------------
On 2026-09-28 a build lost everything it needed because state lived in /tmp:
`/tmp/gold.config` is the config the build restores `.config` from, and a /tmp
sweep removed it. The symptom was two full kernel builds producing a
byte-identical Image while reporting rc=0, because the guard silently fell back
to "no gold, build on whatever .config happens to be". The tab lost its scripts
from /tmp the same way, twice, in one session.

/tmp is not a place to keep anything you would miss. This check is wired into
the build so the regression cannot come back silently.

    no-tmp-state.py            # check the tracked tooling, non-zero if dirty
    no-tmp-state.py --fix      # report, and list the intended replacements
"""
from __future__ import annotations

import os
import re
import sys

ROOT = "/home/host/opikernel"

# Files that must never keep state in /tmp. Excludes anything intentionally
# ephemeral (a board-side /var/tmp scratch is fine; see ALLOW below).
TARGETS = [
    "scripts/kdir-build.sh",
    "scripts/stage-465g-i2c-probe.py",
    "scripts/mirror-32g-boot.sh.py",
    "scripts/kconfig-set.sh",
    "scripts/kconfig-audit.py",
    "scripts/tell-nick.py",
    "pvrgl-work/ser-stream.py",
    "pvrgl-work/ser-push.py",
    "pvrgl-work/ser-push-big.py",
    "pvrgl-work/serping.py",
    "pvrgl-work/dmesgpat.py",
]

# Things that are allowed to look like /tmp but are not:
#  - /var/tmp/...  (survives reboot, board-side scratch for serial transfers)
#  - mktemp -t
ALLOW = re.compile(r"/var/tmp/|mktemp")

# A real offender: /tmp/ used as a path, not inside a comment.
OFFEND = re.compile(r"(?<![\w/])/tmp/(?!tmp\b)")


def main() -> int:
    bad = 0
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, errors="replace") as f:
            for n, line in enumerate(f, 1):
                code = line.split("#", 1)[0]
                if ALLOW.search(code):
                    continue
                if OFFEND.search(code):
                    print("%s:%d: %s" % (rel, n, line.rstrip()[:110]))
                    bad += 1
    if bad:
        print("\nFAIL: %d /tmp state reference(s). State in /tmp is lost on a "
              "sweep or reboot - use /home/host/opikernel/state/ on the host, "
              "/var/tmp on the board." % bad)
        return 1
    print("OK: no /tmp state in project tooling")
    return 0


if __name__ == "__main__":
    sys.exit(main())
