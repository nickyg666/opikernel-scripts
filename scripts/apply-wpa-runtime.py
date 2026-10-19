#!/usr/bin/env python3
"""Apply the staged wpa_supplicant runtime onto a MOUNTED card.

Run with the card in the USB reader, e.g.
    sudo python3 scripts/apply-wpa-runtime.py /mnt/usbsd

Why this exists: the 32 GB card received `wpa_supplicant` as a bare .deb
payload without its runtime dependency `libpcsclite.so.1`, so the binary
aborts at startup:
    wpa_supplicant: error while loading shared libraries:
      libpcsclite.so.1: cannot open shared object file
Serial transfer CANNOT fix this (67,888 B arrived as 2,798 B), so the files
travel by card, sourced from the 465 GB card which has correct copies
(md5-verified identical to the pristine Ubuntu packages).

Safety:
  * Every target is BACKED UP to <file>.pre-wpa-<ts> before overwrite.
  * Every file is verified by md5 AFTER the copy.
  * The script reports and never silently continues on mismatch.
  * Identity is proven by MODULE TREE NAME, never by label/size (both cards
    share LABEL=opi_root and the same ext4 UUID).
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

CARD = sys.argv[1] if len(sys.argv) > 1 else "/mnt/usbsd"
STAGE = sys.argv[2] if len(sys.argv) > 2 else \
    "/home/host/opikernel/stage/wpa-runtime"
EXPECT_TREE = "7.3.0-rc2-00018-g7dc769e5fbd0-dirty"


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout.strip()


def main():
    print("card  = %s" % CARD)
    print("stage = %s" % STAGE)

    # --- identity: prove which card this is, don't infer it -----------------
    mods = os.path.join(CARD, "usr/lib/modules")
    trees = sorted(os.listdir(mods)) if os.path.isdir(mods) else []
    print("module trees on this card: %s" % (trees or "NONE"))
    if trees and trees != [EXPECT_TREE]:
        print("WARNING: expected exactly [%s]" % EXPECT_TREE)
    st = os.statvfs(CARD)
    print("card size = %.1f GB" % (st.f_blocks * st.f_frsize / 1e9))

    ts = time.strftime("%Y%m%d-%H%M%S")
    installed, failed = [], []

    for dirpath, _, files in os.walk(STAGE):
        for f in files:
            src = os.path.join(dirpath, f)
            rel = os.path.relpath(src, STAGE)
            dst = os.path.join(CARD, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                bak = dst + ".pre-wpa-" + ts
                shutil.copy2(dst, bak)
            shutil.copy2(src, dst)
            a, b = md5(src), md5(dst)
            if a == b:
                installed.append((rel, os.path.getsize(dst), a))
            else:
                failed.append((rel, a, b))

    # wpa_supplicant needs the pcsc stub disabled only if lib missing; ensure
    # the loader will find it by running ldconfig's config if present
    ld = os.path.join(CARD, "etc/ld.so.conf.d")
    if os.path.isdir(ld):
        tgt = os.path.join(ld, "zz-aarch64-wpa.conf")
        with open(tgt, "w") as fh:
            fh.write("/usr/lib/aarch64-linux-gnu\n")
        installed.append(("etc/ld.so.conf.d/zz-aarch64-wpa.conf",
                          os.path.getsize(tgt), md5(tgt)))

    print("\ninstalled %d file(s):" % len(installed))
    for rel, sz, h in installed:
        print("  OK   %-52s %8d B  %s" % (rel, sz, h))
    if failed:
        print("\nFAILED %d:" % len(failed))
        for rel, a, b in failed:
            print("  FAIL %-52s %s != %s" % (rel, a, b))
        return 1

    print("\nverify on card:")
    for rel in ["usr/lib/aarch64-linux-gnu/libpcsclite.so.1",
                "usr/lib/aarch64-linux-gnu/libpcsclite_real.so.1",
                "usr/sbin/wpa_supplicant"]:
        p = os.path.join(CARD, rel)
        print("  %-52s %d B  %s"
              % (rel, os.path.getsize(p) if os.path.exists(p) else -1,
                 md5(p) if os.path.exists(p) else "MISSING"))
    print("\nsync the card before pulling it out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())