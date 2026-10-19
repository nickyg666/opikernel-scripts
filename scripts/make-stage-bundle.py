#!/usr/bin/env python3
"""Build the complete, verified stage bundle for the wlan_regon test run.

Nick, 2026-10-04: "you should really be staging ahead not behind like this".
This script exists so that every artifact for a test run is built, hashed and
sitting in ONE directory BEFORE the card is pulled. The card pull becomes a
single verify-and-copy, never a debugging session.

It never touches a card. It only assembles + verifies the payload, and prints
the exact command to install it.

Run:  python3 scripts/make-stage-bundle.py <outdir>
"""
import hashlib
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

KDIR = pathlib.Path("/home/host/kernel-trees/host-build/mainline-7.3")
OPK = pathlib.Path("/home/host/opikernel")
STAGE_SCR = OPK / "scripts/stage-465g-i2c-probe.py"
TEMPLATE = OPK / "pvrgl-work/boot.cmd.live"

RELEASE = "7.3.0-rc2-00018-g7dc769e5fbd0-dirty"

# name -> (source path, expected magic or None)
ITEMS = {
    "Image": (KDIR / "arch/arm64/boot/Image", b"\x1f\x20\x03\xd5"),
    "sun60i-a733-orangepi-zero3w.dtb":
        (KDIR / "arch/arm64/boot/dts/allwinner/"
                "sun60i-a733-orangepi-zero3w.dtb", b"\xd0\x0d\xfe\xed"),
    "aic8800_fdrv.ko": (KDIR / "drivers/net/wireless/aic8800/"
                                 "aic8800_fdrv/aic8800_fdrv.ko", None),
    "aic8800_bsp.ko": (KDIR / "drivers/net/wireless/aic8800/"
                                "aic8800_bsp/aic8800_bsp.ko", None),
}

# Markers that MUST be present, so a stale artifact cannot be staged.
MARKERS = {
    "Image": [b"wlan_regon gpio"],
    "sun60i-a733-orangepi-zero3w.dtb": [b"wlan_regon_default"],
    "aic8800_fdrv.ko": [b"scanres:", b"scancfm:"],
}


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def vermagic(p):
    return subprocess.run(["modinfo", "-F", "vermagic", str(p)],
                          capture_output=True, text=True).stdout.strip()


def cp_b_len(scr):
    """Extract the cp.b length from a generated boot.scr."""
    d = pathlib.Path(scr).read_bytes()[64:].decode("utf-8", "replace")
    m = re.search(r"^cp\.b\s+\S+\s+\S+\s+0x([0-9a-fA-F]+)$", d, re.M)
    return int(m.group(1), 16) if m else None


def blacklist(scr):
    d = pathlib.Path(scr).read_bytes()[64:].decode("utf-8", "replace")
    m = re.search(r"modprobe\.blacklist=\S+", d)
    return m.group(0) if m else None


def load_stage_module():
    spec = importlib.util.spec_from_file_location("s465", STAGE_SCR)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    except Exception:
        pass
    return m


def fdt_addr_for(image_size):
    """Compute the DTB load address from the Image size.

    2026-10-04 opiz3w: the DTB used to be a hardcoded 0x43000000. That is
    only safe by accident:

      * with the old 44,117,880 B self-contained Image, the kernel load
        window (0x41000000 + size) reached 0x42A11808 and the DTB at
        0x43000000 sat INSIDE it - a silent overwrite, no U-Boot error;
      * with today's ~25 MB Image there is 8.5 MB of headroom, but that is a
        coincidence, not a design. Any kernel growth re-creates the overlap.

    Moving it "high" is only safe within the 32-bit U-Boot ceiling:
      * 0x48000000 (tried 2026-10-04) is ABOVE the 0x43999999 hard ceiling
        and U-Boot refuses the fdt entirely;
      * the skill (opiz3w-card-repair) records the initrd ceiling as
        0x43300000 and the hard ceiling as 0x43999999.

    So: 1 MiB aligned, as high as the ceiling allows, leaving room for the
    `fdt resize 65536` the skill requires before booti. Every constraint is
    asserted - this function is the safety, not a comment.
    """
    LOAD = 0x41000000          # where ext4load puts the Image
    COPY = 0x40200000          # where cp.b relocates it (BL31 next-image addr)
    CEIL = 0x43999999          # hard 32-bit U-Boot limit
    INITRD_MAX = 0x43300000    # documented initrd ceiling
    ALIGN = 0x100000           # 1 MiB
    RESERVE = 0x10000          # room for `fdt resize 65536`

    addr = ((CEIL - RESERVE) // ALIGN) * ALIGN

    assert addr >= INITRD_MAX, "fdt below documented initrd ceiling"
    assert addr + RESERVE <= CEIL, "fdt above hard U-Boot ceiling"
    assert addr > LOAD + image_size, "fdt inside the kernel load window"
    assert addr > COPY + image_size, "fdt inside the relocated kernel window"
    return addr


def make_boot_scr_465(image, out):
    """Build boot.scr using the 465 GB card's SELF-CORRECTING form.

    The 465G card's boot.scr uses:

        cp.b 0x41000000 0x40200000 $filesize

    i.e. U-Boot substitutes the load size at run time. That is strictly
    better than a hardcoded hex length, which is what silently truncated the
    kernel before (stage-465g-i2c-probe.py's own comment records that trap:
    cp.b said 0x2A00000 while the Image was 0x2A11808 -> 71,688 bytes short,
    no U-Boot error, no serial line, every downstream check still passing).

    A fresh Image here is 24,811,528 B where the card's was 44,177,416 B, so
    any hardcoded length is wrong the moment the kernel is rebuilt. Use
    $filesize and the card is immune.

    The DTB address is likewise COMPUTED from the Image size (see
    fdt_addr_for) instead of hardcoded, so a kernel that grows past 0x43000000
    can never silently overwrite the device tree.
    """
    import re
    import subprocess

    n = pathlib.Path(image).stat().st_size
    fdt = fdt_addr_for(n)
    src = OPK / "pvrgl-work/boot.cmd.live"
    body = src.read_text()
    # replace any hardcoded cp.b length with $filesize
    body = re.sub(r"^(cp\.b\s+\S+\s+\S+\s+)0x[0-9a-fA-F]+\s*$",
                  lambda m: m.group(1) + "$filesize\n", body, flags=re.M)
    # replace the fdt address with the computed one, in both `fdt addr` and
    # the `ext4load`/`booti` lines that reference it
    body = re.sub(r"^(ext4load mmc 0:1 )0x[0-9a-fA-F]+(\s+boot/mainline/sun60i)",
                  lambda m: m.group(1) + "0x%08X" % fdt + m.group(2),
                  body, flags=re.M)
    body = re.sub(r"^(fdt addr )0x[0-9a-fA-F]+\s*$",
                  lambda m: m.group(1) + "0x%08X" % fdt + "\n",
                  body, flags=re.M)
    body = re.sub(r"^(booti 0x[0-9a-fA-F]+ - )0x[0-9a-fA-F]+\s*$",
                  lambda m: m.group(1) + "0x%08X" % fdt + "\n",
                  body, flags=re.M)
    cmd = pathlib.Path(str(out) + ".cmd")
    cmd.write_text(body)
    subprocess.run(["mkimage", "-A", "arm", "-T", "script", "-O", "linux",
                    "-n", "OPiZ3W", "-C", "none", "-d", str(cmd), str(out)],
                   check=True, capture_output=True)
    d = pathlib.Path(out).read_bytes()[64:].decode("utf-8", "replace")
    if "$filesize" not in d:
        fail("generated boot.scr does not use $filesize")
    if "modprobe.blacklist" not in d:
        fail("generated boot.scr has no modprobe.blacklist")
    # ceiling check on the real size
    if 0x40200000 + n > 0x43999999:
        fail("kernel copy would pass the 32-bit U-Boot ceiling")

    # Verify the DTB placement in the GENERATED script, by reading it back,
    # against every constraint fdt_addr_for asserts. A boot.scr that looks
    # right in source but carries a stale hardcoded address is exactly the
    # failure this whole change exists to prevent.
    import re as _re
    m = _re.search(r"^fdt addr (0x[0-9a-fA-F]+)\s*$", d, _re.M)
    if not m:
        fail("generated boot.scr has no 'fdt addr' line")
    got = int(m.group(1), 16)
    want = fdt_addr_for(n)
    if got != want:
        fail("fdt addr 0x%08X in boot.scr != computed 0x%08X" % (got, want))

    # every reference to the DTB must agree, or booti gets a different
    # address than the one fdt addr selected
    for pat, label in ((r"^ext4load mmc 0:1 (0x[0-9a-fA-F]+)\s+boot/mainline/sun60i",
                        "ext4load"),):
        mm = _re.search(pat, d, _re.M)
        if not mm:
            fail("boot.scr missing the DTB %s line" % label)
        if int(mm.group(1), 16) != want:
            fail("boot.scr %s DTB addr 0x%08X != fdt addr 0x%08X"
                 % (label, int(mm.group(1), 16), want))
    mb = _re.search(r"^booti 0x[0-9a-fA-F]+ - (0x[0-9a-fA-F]+)\s*$", d, _re.M)
    if not mb:
        fail("boot.scr has no booti line with a DTB address")
    if int(mb.group(1), 16) != want:
        fail("booti DTB addr 0x%08X != fdt addr 0x%08X"
             % (int(mb.group(1), 16), want))

    if want + 0x10000 <= 0x41000000 + n:
        fail("DTB at 0x%08X overlaps the kernel load window" % want)
    return n


def fail(msg):
    print("BUNDLE_FAIL: %s" % msg)
    sys.exit(1)


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                       "/home/host/opikernel/stage/wlan-regon-run")
    out.mkdir(parents=True, exist_ok=True)
    print("bundle = %s\n" % out)

    # ---- 1. kernel artifacts ------------------------------------------
    for name, (src, magic) in ITEMS.items():
        if not src.exists():
            fail("missing source %s" % src)
        dst = out / name
        shutil.copy2(src, dst)
        data = dst.read_bytes()
        if magic and data[:4] != magic:
            fail("%s magic %s != %s" % (name, data[:4].hex(), magic.hex()))
        for mk in MARKERS.get(name, []):
            if mk not in data:
                fail("%s is missing marker %r - stale artifact?" % (name, mk))
        print("  %-38s %10d B  %s" % (name, len(data), md5(dst)))

    # ---- 2. modules must match the running kernel ---------------------
    for ko in ("aic8800_fdrv.ko", "aic8800_bsp.ko"):
        vm = vermagic(out / ko)
        if not vm.startswith(RELEASE):
            fail("%s vermagic %r does not start with %s"
                 % (ko, vm, RELEASE))
        print("  %-38s vermagic OK (%s)" % (ko, vm.split()[0]))

    # ---- 3. boot.scr generated FROM this Image ------------------------
    img = out / "Image"
    # Uses the 465G card's self-correcting `cp.b ... $filesize` form so a
    # rebuilt Image of a different size can never be silently truncated.
    n = make_boot_scr_465(img, out / "boot.scr")
    if n != img.stat().st_size:
        fail("bundle Image %d != measured size %d" % (img.stat().st_size, n))
    bl = blacklist(out / "boot.scr")
    if not bl:
        fail("boot.scr has NO modprobe.blacklist - the board wedges on "
             "autoload. Fix pvrgl-work/boot.cmd.live first.")
    d = (out / "boot.scr").read_bytes()[64:].decode("utf-8", "replace")
    print("  %-38s %10d B  cp.b=$filesize (self-correcting), Image %d"
          % ("boot.scr", (out / "boot.scr").stat().st_size, n))
    print("  %-38s %s" % ("", bl))

    # ---- 4. manifest --------------------------------------------------
    lines = ["# opiz3w wlan_regon test bundle  %s" % time.strftime("%F %T"),
             "# release %s" % RELEASE, ""]
    for p in sorted(out.iterdir()):
        if p.name == "MANIFEST.md5" or p.is_dir():
            continue
        lines.append("%s  %s" % (md5(p), p.name))
    (out / "MANIFEST.md5").write_text("\n".join(lines) + "\n")
    print("\n--- MANIFEST ---")
    print("\n".join(lines))

    # ---- 5. self-check: re-read everything from disk ------------------
    bad = 0
    for p in sorted(out.iterdir()):
        if p.name == "MANIFEST.md5" or p.is_dir():
            continue
        want = dict(
            (ln.split()[1], ln.split()[0])
            for ln in (out / "MANIFEST.md5").read_text().splitlines()
            if not ln.startswith("#") and ln.strip())
        if want.get(p.name) != md5(p):
            print("  REVERIFY FAIL %s" % p.name)
            bad += 1
    print("\nself-check: %s" % ("ALL VERIFIED" if not bad
                                else "%d MISMATCH" % bad))
    print("\nINSTALL WITH:\n  sudo python3 %s/scripts/apply-stage-bundle.py %s"
          % (OPK, out))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())