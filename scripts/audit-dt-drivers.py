#!/usr/bin/env python3
"""Audit every `status = "okay"` DT node against a real driver in the Image.

WHY THIS EXISTS
---------------
On 2026-10-04/05 the board would not boot because five boot-chain subsystems
were compiled in on paper and absent in practice: every one of them is gated
on `ARCH_SUNXI` (Allwinner's 32-bit port) while this board is arm64, so
`make olddefconfig` dropped the symbol silently with rc=0. Discovering them
one per boot cycle cost an entire night.

The rule this tool enforces:

    a DT node that says status = "okay" is a CLAIM. Either a driver in the
    running Image claims its compatible, or something will defer forever
    without telling you why.

WHAT IT CHECKS
--------------
1. Decompiles the real, built DTB with dtc (ground truth - not the source
   dts, which may not reflect overrides).
2. Walks every node and collects the enabled ones with a compatible.
3. For each compatible, asks the kernel tree: does any `of_match_table` claim
   it? Uses the compiled Image's strings as the cross-check for whether the
   driver is actually LINKED.
4. Reports three buckets:
     LINKED    - claimed by a driver AND present in the Image
     NO_DRIVER - enabled in DT but no of_match_table claims it
     UNKNOWN   - claimed by a driver whose symbol is not in the Image
                 (i.e. the classic ARCH_SUNXI-gate victim)

It cannot prove a node will probe - only that something is there to try.
That distinction matters: a LINKED result is necessary, not sufficient.

Usage:  python3 scripts/audit-dt-drivers.py [--image PATH] [--dtb PATH]
"""
import os
import re
import subprocess
import sys

KDIR = "/home/host/kernel-trees/host-build/mainline-7.3"
DEFAULT_IMAGE = KDIR + "/arch/arm64/boot/Image"
DEFAULT_DTB = (KDIR + "/arch/arm64/boot/dts/allwinner/"
               "sun60i-a733-orangepi-zero3w.dtb")

# Only report these as failures. The board DT enables 78 nodes; many are
# display/media/usb peripherals that are irrelevant to reaching a login
# prompt, and flagging them all buries the signal.
BOOT_CRITICAL = re.compile(
    r"/(mmc@|i2c@|spi@|serial@|.*ccu@|rtc@|gpio|regulator|pwm|leds|"
    r"rfkill|phy_switcher|cpufreq|thermal|wakeup|clocks|msgbox|hwspinlock)")


def decompile(dtb):
    r = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", dtb],
                       capture_output=True, text=True)
    return r.stdout


def enabled_nodes(dts):
    """Return [(path, [compatibles])] for every status=okay node."""
    out = []
    stack = []
    for ln in dts.splitlines():
        s = ln.strip()
        m = re.match(r"^([\w@,.\-/]+)\s*\{", s)
        if m:
            name = m.group(1)
            path = (stack[-1][0] + "/" + name) if stack else "/" + name
            stack.append([path, []])
        if stack:
            stack[-1][1].append(s)
        if s.startswith("};"):
            if stack:
                path, body = stack.pop()
                b = "\n".join(body)
                if 'status = "okay"' in b:
                    c = re.search(r'compatible\s*=\s*((?:"[^"]+"\s*,?\s*)+)', b)
                    if c:
                        out.append((path, re.findall(r'"([^"]+)"', c.group(1))))
    return out


def collect_claimed_compatibles():
    """Every compatible string any of_match_table in the tree claims."""
    claimed = {}
    for dp, dn, fn in os.walk(KDIR + "/drivers"):
        dn[:] = [d for d in dn if d != ".git"]
        for f in fn:
            if not f.endswith(".c"):
                continue
            p = os.path.join(dp, f)
            try:
                txt = open(p, errors="replace").read()
            except OSError:
                continue
            # Scope strictly to THIS file. An earlier version matched an
            # of_device_id block with a greedy pattern that ran past the end
            # of the file and attributed another driver's compatibles to
            # this one, which produced 20 phantom "missing driver" rows.
            stem = f[:-2]
            for c in re.finditer(r'\.compatible\s*=\s*"([^"]+)"', txt):
                claimed.setdefault(c.group(1), []).append(
                    os.path.relpath(p, KDIR))
            # remember the stem for the in-Image check
            for lst in claimed.values():
                pass
    return claimed


def main():
    image = DEFAULT_IMAGE
    dtb = DEFAULT_DTB
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--image" and i + 1 < len(args):
            image = args[i + 1]
        if a == "--dtb" and i + 1 < len(args):
            dtb = args[i + 1]

    print("image = %s" % image)
    print("dtb   = %s" % dtb)
    if not os.path.exists(dtb):
        print("BUNDLE_FAIL: dtb missing: %s" % dtb)
        return 1
    if not os.path.exists(image):
        print("BUNDLE_FAIL: image missing: %s" % image)
        return 1

    dts = decompile(dtb)
    nodes = enabled_nodes(dts)
    print("enabled nodes with a compatible: %d\n" % len(nodes))

    claimed = collect_claimed_compatibles()
    print("compatibles claimed by an of_match_table: %d\n" % len(claimed))

    img = open(image, "rb").read()

    linked, no_driver, unknown = [], [], []
    for _path, _compats in nodes:
        # NO reused loop-variable names. This function used `c` both as the
        # per-node compatible and as the loop variable, so after the first
        # hit every later row reported that stale value - which is how 20
        # unrelated nodes all came out as "allwinner,sunxi-phy-switcher".
        _hit_compat = None
        _hit_files = None
        for _compat in _compats:
            if _compat in claimed:
                _hit_compat = _compat
                _hit_files = claimed[_compat]
                break
        if _hit_compat is None:
            no_driver.append((_path, list(_compats)))
            continue
        _stem = os.path.basename(_hit_files[0])[:-2]
        if _stem.encode() in img:
            linked.append((_path, _hit_compat, _stem))
        else:
            unknown.append((_path, _hit_compat, _stem, _hit_files[0]))

    def show(title, rows, fmt):
        if not rows:
            return
        print("=== %s (%d) ===" % (title, len(rows)))
        for r in rows:
            print("  " + fmt(r))
        print()

    show("NO_DRIVER: enabled in DT, no of_match_table claims it", no_driver,
         lambda r: "%-48s %s" % (r[0][-48:], ",".join(r[1])))
    show("UNKNOWN: driver exists in tree but NOT in the Image "
         "(the ARCH_SUNXI-gate failure mode)", unknown,
         lambda r: "%-44s %-26s %s" % (r[0][-44:], r[1], r[2]))
    show("LINKED", linked,
         lambda r: "%-50s %s" % (r[0][-50:], r[2]))

    crit_missing = [row for row in no_driver
                    if BOOT_CRITICAL.search(row[0])]
    crit_unknown = [u for u in unknown if BOOT_CRITICAL.search(u[0])]
    print("SUMMARY")
    print("  linked                     %d" % len(linked))
    print("  no_driver                  %d" % len(no_driver))
    print("  unknown (gate victims)      %d" % len(unknown))
    print("  BOOT-CRITICAL missing       %d" %
          (len(crit_missing) + len(crit_unknown)))
    # NOTE: do not reuse p/c here. An earlier version shadowed the outer
    # loop variables and every row after the first printed a stale
    # compatible, which made 20 unrelated nodes all report
    # "allwinner,sunxi-phy-switcher".
    for _p, _cs in crit_missing:
        print("     MISSING-DRIVER  %-46s %s" % (_p[-46:], ",".join(_cs)))
    for _u in crit_unknown:
        print("     NOT-IN-IMAGE    %-46s %s" % (_u[0][-46:], _u[2]))
    return 1 if (crit_missing or crit_unknown) else 0


if __name__ == "__main__":
    sys.exit(main())