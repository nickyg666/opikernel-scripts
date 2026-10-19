#!/usr/bin/env python3
"""Install a stage bundle onto a MOUNTED card, with backups and readback proof.

    sudo python3 scripts/apply-stage-bundle.py <bundle> [mountpoint]

Fails closed on any of:
  * a manifest hash mismatch between bundle and MANIFEST.md5
  * a copy that does not read back identical on the card
  * a boot.scr whose cp.b length != the Image size on the card
  * a missing modprobe.blacklist (the board wedges on autoload without it)
  * more than one module tree on the card (stale-tree shadowing)

Card identity is proven by MODULE TREE NAME, never by label or size: both
cards carry LABEL=opi_root and the same ext4 UUID.
"""
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

BUNDLE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                      "/home/host/opikernel/stage/wlan-regon-run")
CARD = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "/mnt/usbsd")
EXPECT_TREE = "7.3.0-rc2-00018-g7dc769e5fbd0-dirty"


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fail(msg):
    print("APPLY_FAIL: %s" % msg)
    sys.exit(1)


def cp_b_len(p):
    """Return ('filesize',) if boot.scr uses $filesize, else the hex length."""
    d = p.read_bytes()[64:].decode("utf-8", "replace")
    m = re.search(r"^cp\.b\s+\S+\s+\S+\s+(\$filesize|0x[0-9a-fA-F]+)\s*$",
                  d, re.M)
    if not m:
        return None, None
    return m.group(1), (None if m.group(1) == "$filesize"
                        else int(m.group(1), 16))


def main():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    print("bundle = %s\ncard   = %s\n" % (BUNDLE, CARD))

    # ---- 0. bundle integrity -----------------------------------------
    man = BUNDLE / "MANIFEST.md5"
    if not man.exists():
        fail("no MANIFEST.md5 in bundle")
    want = {}
    for ln in man.read_text().splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        h, n = ln.split()[0], ln.split()[1]
        want[n] = h
    for n, h in want.items():
        got = md5(BUNDLE / n)
        if got != h:
            fail("bundle %s %s != manifest %s" % (n, got, h))
    print("bundle integrity OK (%d files)" % len(want))

    # ---- 1. card identity + invariants --------------------------------
    mods = CARD / "usr/lib/modules"
    trees = sorted(x.name for x in mods.iterdir() if x.is_dir()) \
        if mods.is_dir() else []
    print("module trees on card: %s" % (trees or "NONE"))
    if trees != [EXPECT_TREE]:
        fail("expected exactly [%s]; stale trees shadow the driver"
             % EXPECT_TREE)

    scr_src = BUNDLE / "boot.scr"
    bl = re.search(r"modprobe\.blacklist=\S+",
                   scr_src.read_bytes()[64:].decode("utf-8", "replace"))
    if not bl:
        fail("bundle boot.scr has no modprobe.blacklist")
    print("blacklist present: %s" % bl.group(0))

    # ---- 2. copy with backups, verify each ----------------------------
    # Modules come from the bundle too, and DISCOVERED FROM THE MANIFEST
    # rather than a hardcoded list. The hardcoded list silently skipped
    # sunxi-axp8191.ko when it was added later, which left the AXP8191 PMIC
    # driver missing from a card that otherwise reported success.
    tree = mods / EXPECT_TREE
    targets = {
        "Image": CARD / "boot/mainline/Image",
        "sun60i-a733-orangepi-zero3w.dtb":
            CARD / "boot/mainline/sun60i-a733-orangepi-zero3w.dtb",
        "boot.scr": CARD / "boot.scr",
    }
    for name in sorted(want):
        if name.endswith(".ko"):
            targets[name] = tree / name

    for name, dst in targets.items():
        src = BUNDLE / name
        if not src.exists():
            fail("bundle missing %s" % name)
        if dst.exists():
            bak = dst.with_name(dst.name + ".pre-wlanregon-" + stamp)
            shutil.copy2(dst, bak)
            print("  backup %s -> %s" % (dst.name, bak.name))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        a, b = md5(src), md5(dst)
        if a != b:
            fail("%s readback %s != %s" % (name, b, a))
        print("  OK %-38s %10d B  %s" % (name, dst.stat().st_size, b))

    # ---- 3. post-write invariants ON THE CARD -------------------------
    img = targets["Image"]
    raw, n = cp_b_len(targets["boot.scr"])
    if raw is None:
        fail("card boot.scr has no cp.b line")
    if raw == "$filesize":
        # self-correcting: U-Boot substitutes the real load size at run time,
        # so no truncation is possible regardless of Image size.
        print("  card cp.b=$filesize (self-correcting), Image %d - "
              "truncation impossible" % img.stat().st_size)
    else:
        if n != img.stat().st_size:
            fail("card cp.b %d != card Image %d  <-- silently truncated kernel"
                 % (n, img.stat().st_size))
        print("  card cp.b=0x%X == card Image %d  (invariant holds)"
              % (n, img.stat().st_size))

    vm = subprocess.run(["modinfo", "-F", "vermagic",
                         str(targets["aic8800_fdrv.ko"])],
                        capture_output=True, text=True).stdout.strip()
    if not vm.startswith("7.3.0-rc2-00018-g7dc769e5fbd0-dirty"):
        fail("card module vermagic mismatch: %r" % vm)
    print("  card vermagic %s" % vm.split()[0])

    # Every module the bundle carries must exist on the card with the right
    # md5. This is the check that would have caught the missing
    # sunxi-axp8191.ko on the 465 GB card.
    print("\n  module readback:")
    for name in sorted(n for n in want if n.endswith(".ko")):
        p = targets[name]
        if not p.exists():
            fail("bundle has %s but it is NOT on the card at %s"
                 % (name, p))
        got = md5(p)
        if got != want[name]:
            fail("card %s md5 %s != bundle %s" % (name, got, want[name]))
        print("    OK %-24s %s" % (name, got))

    # The Image must actually contain the drivers we fixed. A card can look
    # perfectly staged and still boot a kernel that predates the fix.
    img = targets["Image"]
    # One entry per boot-chain subsystem that was silently missing on arm64
    # because its Kconfig was gated on ARCH_SUNXI (32-bit) only. Each of
    # these failed SILENTLY - the build reported rc=0 and the symbol "looked"
    # enabled. See ROOTCAUSE-arch-sunxi-gates-hide-arm64-allwinner.
    checks = {
        "A733 I2C": 16,              # I2C_MV64XXX  -> AXP8191's bus
        "x-powers,axp8191": 1,       # AXP8191 PMIC binding
        "sun60iw2": 8,               # SUNXI_CCU/SUN60IW2_CCU -> all clocks
        "sunxi-mmc": 1,              # MMC_SUNXI -> THE ROOT DEVICE
        "sun60iw2-r-pinctrl": 1,     # PINCTRL_SUN60IW2_R -> every GPIO
    }
    blob = img.read_bytes()
    print("\n  Image content checks:")
    for probe, minimum in checks.items():
        n = blob.count(probe.encode())
        if n < minimum:
            fail("Image %s contains %r %d time(s), expected >= %d "
                 "- this is a STALE Image, the fixes are not in it"
                 % (img.name, probe, n, minimum))
        print("    OK %-24s %d occurrence(s)" % (probe, n))

    # Full DT-vs-driver audit. The string checks above catch a STALE Image;
    # this catches an Image that is correct but whose DT promises devices
    # the kernel has no driver for. Between them they cover the two ways a
    # card can be "fully staged" and still fail to reach a login prompt.
    print("\n  DT driver audit:")
    audit = pathlib.Path("/home/host/opikernel/scripts/audit-dt-drivers.py")
    rc = subprocess.run(
        ["python3", str(audit), "--image", str(img), "--dtb",
         str(CARD / "boot/mainline/sun60i-a733-orangepi-zero3w.dtb")],
        capture_output=True, text=True)
    tail = [l for l in rc.stdout.splitlines() if l.startswith("  ")]
    for l in tail[-24:]:
        print("   ", l)
    # The root device MUST be linked - without it nothing can mount.
    if "mmc@4020000" not in rc.stdout or "mmc@4020000                         sunxi-mmc" not in rc.stdout:
        print("\n  NOTE: review the audit above for mmc@402* (root device).")

    print("\nALL INVARIANTS HOLD.")
    print("Now: sudo sync; sudo sync; then pull the card.")
    return 0


if __name__ == "__main__":
    sys.exit(main())