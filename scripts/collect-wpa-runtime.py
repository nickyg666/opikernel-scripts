#!/usr/bin/env python3
"""Copy the missing wpa_supplicant runtime files from the 465G card onto a
SPARE directory that will be merged into the 32G card.

Why: the 32G card was given `wpa_supplicant` as a .deb payload but NOT its
runtime dependency `libpcsclite.so.1`, so the binary cannot start
(`invalid ELF header` when a corrupt 2.8 KB truncated copy was pushed over
serial; `cannot open shared object file` before that).

Serial transfer is NOT viable: a 67,888-byte library arrived as 2,798 bytes.
Everything here moves by card, never by wire.

Identity discipline: cards share LABEL=opi_root and the same ext4 UUID, so
identity is established by MODULE TREE NAME, never by label or size.
"""
import os
import shutil
import subprocess
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "/mnt/usbsd"
DST = sys.argv[2] if len(sys.argv) > 2 else "/home/host/opikernel/stage/wpa-runtime"

# (relative path, mode, must exist & be non-empty)
FILES = [
    ("usr/lib/aarch64-linux-gnu/libpcsclite.so.1", 0o644),
    ("usr/lib/aarch64-linux-gnu/libpcsclite_real.so.1", 0o644),
    ("usr/sbin/wpa_supplicant", 0o755),
    ("usr/sbin/wpa_cli", 0o755),
    ("usr/sbin/wpa_action", 0o755),
]
DIRS = [
    "etc/wpa_supplicant",
]


def md5(p):
    r = subprocess.run(["md5sum", p], capture_output=True, text=True)
    return r.stdout.split()[0] if r.stdout.strip() else "MISSING"


def main():
    os.makedirs(DST, exist_ok=True)
    ok, bad = [], []
    for rel, mode in FILES:
        s = os.path.join(SRC, rel)
        d = os.path.join(DST, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if not os.path.exists(s):
            bad.append((rel, "not on source card"))
            continue
        shutil.copy2(s, d)
        os.chmod(d, mode)
        a, b = md5(s), md5(d)
        (ok if a == b else bad).append(
            (rel, "%d B md5 %s%s" % (os.path.getsize(d), a,
                                     "" if a == b else " != %s" % b)))
    for rel in DIRS:
        s = os.path.join(SRC, rel)
        d = os.path.join(DST, rel)
        os.makedirs(d, exist_ok=True)
        for f in sorted(os.listdir(s)):
            sp = os.path.join(s, f)
            if os.path.isfile(sp):
                shutil.copy2(sp, os.path.join(d, f))
                ok.append((rel + "/" + f, "%d B" % os.path.getsize(sp)))

    print("copied %d, problems %d" % (len(ok), len(bad)))
    for r, why in ok:
        print("  OK   %-56s %s" % (r, why))
    for r, why in bad:
        print("  FAIL %-56s %s" % (r, why))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())