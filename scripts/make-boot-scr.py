#!/usr/bin/env python3
"""
Regenerate stage/7.3-stage/boot.scr with a CORRECTLY DERIVED Image length.

Why this exists: on 2026-09-26 the board crashed at 0.000000s with a level-0
translation fault because boot.scr had a hardcoded `cp.b ... 0x27C6808` from
an older, smaller Image. Enabling USB gadget configfs grew the Image to
41912328 B, so U-Boot copied a truncated kernel.

Per /home/host/.hermes/skills/kernel/SKILL.md:
  * "never overwrite a working card script on the strength of a remembered
     constant"
  * "Compute the end from the Image HEADER's image_size, not `ls -l`
     - BSS beyond EOF adds to the load extent"

So: read image_size from the arm64 Image header (offset 0x10), use that for
the cp.b length, verify the resulting end address is under the U-Boot
ceiling, regenerate with `mkimage -C none`, then READ THE RESULT BACK and
assert the load paths and length are what we intended.

Usage:  python3 make-boot-scr.py [--check]
        --check  only verify the existing boot.scr matches the current Image
"""
import shutil
import struct
import subprocess
import sys
from pathlib import Path

K = Path('/home/host/kernel-trees/host-build/mainline-7.3')
S = Path('/home/host/opikernel/stage/7.3-stage')
IMAGE = K / 'arch/arm64/boot/Image'
DTB_NAME = 'sun60i-a733-orangepi-zero3w.dtb'
BOOT_SCR = S / 'boot.scr'

LOAD = 0x40200000          # where the Image is copied for booti
DTB_SLOT = 0x43000000      # where the DTB is loaded
STAGE_SLOT = 0x41000000    # scratch for ext4load
CEILING = 0x43999999       # U-Boot load ceiling on this board
DTB_RESIZE = 65536


def image_size_from_header(path: Path) -> int:
    """arm64 Image header: 0x08 text_offset(u64), 0x10 image_size(u64)."""
    with path.open('rb') as f:
        hdr = f.read(0x20)
    if len(hdr) < 0x18:
        raise SystemExit('Image too short to hold a header')
    code0, code1 = struct.unpack_from('<II', hdr, 0)
    if code0 != 0xd503201f:
        raise SystemExit(f'not an arm64 Image: code0=0x{code0:08x}')
    return struct.unpack_from('<Q', hdr, 0x10)[0]


def build_cmd(img_len: int) -> str:
    return (
        "OPiZ3W\n"
        "setenv bootargs console=ttyS0,115200 earlycon=uart,mmio32,0x2500000 "
        "root=PARTUUID=486ea4ae-01 rootfstype=ext4 rootwait rw "
        "loglevel=7\n"
        f"ext4load mmc 0:1 0x{STAGE_SLOT:08x} boot/mainline/Image\n"
        f"cp.b 0x{STAGE_SLOT:08x} 0x{LOAD:08x} 0x{img_len:x}\n"
        f"ext4load mmc 0:1 0x{DTB_SLOT:08x} boot/mainline/{DTB_NAME}\n"
        f"fdt addr 0x{DTB_SLOT:08x}\n"
        f"fdt resize {DTB_RESIZE}\n"
        f"booti 0x{LOAD:08x} - 0x{DTB_SLOT:08x}\n"
    )


def verify(scr: Path, img_len: int) -> None:
    out = subprocess.run(['strings', str(scr)], capture_output=True,
                         text=True, timeout=60).stdout
    with scr.open('rb') as f:
        magic = f.read(4)
    problems = []
    if magic != bytes.fromhex('27051956'):
        problems.append(f'bad magic {magic.hex()} (expected 27051956)')
    if f'0x{img_len:x}' not in out:
        problems.append(f'cp.b length 0x{img_len:x} not found in script body')
    for needed in ('boot/mainline/Image', f'boot/mainline/{DTB_NAME}',
                   'fdt resize', 'booti'):
        if needed not in out:
            problems.append(f'missing expected line fragment: {needed}')
    # guard against the /boot/Image and /boot/dtb rewrite bug
    for bad in ('/boot/Image', '/boot/dtb'):
        if bad in out:
            problems.append(f'script rewrote load path to {bad}')
    if problems:
        print('VERIFY FAILED:')
        for p in problems:
            print('  -', p)
        raise SystemExit(1)


def main() -> int:
    img_len = image_size_from_header(IMAGE)
    end = LOAD + img_len
    print(f'Image header image_size = {img_len} (0x{img_len:x})')
    print(f'  ls -l size            = {IMAGE.stat().st_size} (0x{IMAGE.stat().st_size:x})')
    print(f'  end address           = 0x{end:x}   ceiling 0x{CEILING:x}')
    if end > CEILING:
        raise SystemExit(f'Image would exceed the U-Boot ceiling: 0x{end:x}')

    if '--check' in sys.argv:
        if not BOOT_SCR.exists():
            raise SystemExit('no boot.scr to check')
        verify(BOOT_SCR, img_len)
        print('CHECK OK: existing boot.scr matches the current Image')
        return 0

    cmd = build_cmd(img_len)
    tmp_cmd = Path('/tmp/boot.cmd.gen')
    tmp_scr = Path('/tmp/boot.scr.gen')
    tmp_cmd.write_text(cmd)
    p = subprocess.run(['mkimage', '-A', 'arm', '-O', 'linux', '-T', 'script',
                        '-C', 'none', '-n', 'OPiZ3W',
                        '-d', str(tmp_cmd), str(tmp_scr)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        print('mkimage failed:', p.stdout, p.stderr)
        return 1

    verify(tmp_scr, img_len)          # never install an unverified script
    bak = BOOT_SCR.with_name(BOOT_SCR.name + '.bak-pregen')
    if BOOT_SCR.exists():
        shutil.copy2(BOOT_SCR, bak)
        print(f'previous boot.scr kept as {bak.name}')
    # /tmp is often a different filesystem, so os.replace() across the boundary
    # fails with EXDEV. Copy then remove instead of rename.
    shutil.copy2(tmp_scr, BOOT_SCR)
    tmp_scr.unlink(missing_ok=True)
    verify(BOOT_SCR, img_len)         # and again after install
    print(f'installed {BOOT_SCR} ({BOOT_SCR.stat().st_size} B)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
