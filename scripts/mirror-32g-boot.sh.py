#!/usr/bin/env python3
"""Mirror the current 7.3 boot stack onto the 32G aside card in the tab.

The 32G card is the fast-iteration boot card: every current blocker is pre-root
(R-I2C -> PMIC -> regulator -> MMC), so it can carry kernel/DT diagnosis without
touching the 465G production card. Fail-closed on card size, with dated backups,
atomic readback, and a clean unmount.
"""
from __future__ import annotations

import hashlib
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/home/host/opikernel')
K = Path('/home/host/kernel-trees/host-build/mainline-7.3')
S = ROOT / 'stage/7.3-stage'
TAB = 'tab@192.168.0.149'
# scp/ssh staging area ON THE TAB. Not /tmp: the tab reboots and loses it
# mid-investigation (twice), and /tmp gets swept. /var/tmp survives reboot.
# This is a path on the TAB, not on the host.
REMOTE = '/var/tmp/opiz3w-mirror'
ASIDE_MIN = 25_000_000_000
ASIDE_MAX = 450_000_000_000


def kernel_vermagic() -> str:
    """The vermagic of the Image we are shipping, read from the built kernel.
    A module built from a different source state than the Image loads with
    "Invalid module format" even when every symbol resolves - which is what
    happened on 2026-09-26 (7.3.0-rc2-dirty vs 7.3.0-rc2-00001-g125bcaf05287-dirty)."""
    out = subprocess.run(['strings', str(K / 'arch/arm64/boot/Image')],
                         capture_output=True, text=True, timeout=300).stdout
    for line in out.splitlines():
        if line.startswith('Linux version '):
            return line.split(' ', 2)[2].split(' ', 1)[0]
    raise RuntimeError('cannot read kernel release from Image')


def vermagic(ko: Path) -> str:
    out = subprocess.run(['modinfo', '-F', 'vermagic', str(ko)],
                         capture_output=True, text=True, timeout=120).stdout.strip()
    return out.split(' ', 1)[0] if out else ''


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def ssh(script: str, timeout: int = 90):
    args = ['sshpass', '-p', '1', 'ssh', '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=8', TAB, 'sh -s']
    return subprocess.run(args, input=script, text=True, capture_output=True, timeout=timeout)


def scp(src: Path, dst: str):
    args = ['sshpass', '-p', '1', 'scp', '-q', '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null', str(src), TAB + ':' + dst]
    subprocess.run(args, text=True, check=True, timeout=120)


def main():
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    srcs = {
        'Image': K / 'arch/arm64/boot/Image',
        'sun60i-a733-orangepi-zero3w.dtb': K / 'arch/arm64/boot/dts/allwinner/sun60i-a733-orangepi-zero3w.dtb',
        'boot.scr': S / 'boot.scr',
    }
    want = {n: md5(p) for n, p in srcs.items()}
    print('SOURCES', want, flush=True)

    pre = ssh(f'''set -eu
CAND=; COUNT=0
for d in /dev/sda /dev/sdb /dev/sdc; do
  [ -b "$d" ] || continue
  n=$(lsblk -b -dn -o SIZE "$d" 2>/dev/null | tr -d '[:space:]' || true)
  case "$n" in ''|*[!0-9]*) continue ;; esac
  if [ "$n" -ge {ASIDE_MIN} ] && [ "$n" -lt {ASIDE_MAX} ]; then CAND="$d"; COUNT=$((COUNT+1)); fi
done
[ "$COUNT" -eq 1 ] || {{ echo "NO_UNIQUE_32G COUNT=$COUNT"; exit 2; }}
[ -b "$CAND"1 ] || {{ echo "NO_PARTITION $CAND"; exit 2; }}
echo "PREFLIGHT_OK CARD=$CAND SIZE=$n"
''')
    if pre.returncode != 0:
        print(pre.stdout + pre.stderr)
        raise RuntimeError('aside preflight failed')
    print(pre.stdout.strip())
    card = pre.stdout.split('CARD=', 1)[1].split()[0]

    if ssh('mkdir -p ' + REMOTE + '/boot/mainline\n').returncode != 0:
        raise RuntimeError('remote dir failed')
    scp(srcs['Image'], REMOTE + '/boot/mainline/Image')
    scp(srcs['sun60i-a733-orangepi-zero3w.dtb'], REMOTE + '/boot/mainline/sun60i-a733-orangepi-zero3w.dtb')
    scp(srcs['boot.scr'], REMOTE + '/boot.scr')
    # 2026-09-26: ship BOTH aic8800 modules. aic8800_fdrv needs symbols that
    # live in aic8800_bsp.ko, so shipping only fdrv gives an Unknown symbol
    # error (aicwf_prealloc_txq_alloc, dpd_res, aicbsp_resv_mem_alloc_skb).
    # 2026-09-26: PowerVR rogue firmware. powervr.ko requests
    # powervr/rogue_36.5x.104.*_v1.fw (modinfo -F firmware). Without it the
    # GPU driver loads but never initialises.
    pwfw = S / 'lib/firmware/powervr'
    if pwfw.is_dir():
        ssh(f'mkdir -p {REMOTE}/lib/firmware/powervr\n')
        for blob in sorted(pwfw.iterdir()):
            scp(blob, REMOTE + '/lib/firmware/powervr/' + blob.name)
            print('PVRFW_STAGE', blob.name, md5(blob))
    # 2026-09-26: ship the aic8800 firmware too. The driver calls
    # request_firmware("aic8800d80/aic_userconfig_8800d80.txt") and dies on
    # -ENOENT without it, so modules alone are not enough.
    fwdir = S / 'fw/aic8800d80'
    if fwdir.is_dir():
        ssh(f'mkdir -p {REMOTE}/lib/firmware/aic8800d80\n')
        for blob in sorted(fwdir.iterdir()):
            scp(blob, REMOTE + '/lib/firmware/aic8800d80/' + blob.name)
            print('FW_STAGE', blob.name, md5(blob))
    # Install into both the release-named dir (modprobe uses $(uname -r)) and the
    # plain one. Both vermagics are asserted to match before shipping.
    KVERMAGIC = kernel_vermagic()
    KREL = KVERMAGIC
    kos = sorted((S / 'lib/modules/7.3.0-rc2-dirty').glob('aic8800*.ko'))
    kos += sorted((S / 'lib/modules/7.3.0-rc2-dirty').glob('sunxi_rfkill*.ko'))
    # 2026-09-26: the PowerVR GPU module. CONFIG_DRM_POWERVR=m and the
    # gpu@1800000 node (img,img-bxm-4-64 / img,img-rogue) had NO driver
    # bound at all - /dev/dri did not exist. Ship powervr.ko with its rogue
    # firmware or the GPU stays dead.
    kos += sorted((S / 'lib/modules/7.3.0-rc2-dirty').glob('powervr*.ko'))
    # 2026-09-26: powervr's real module deps (MODULE_INFO depends =
    # "gpu-sched,drm_gpuvm,drm_shmem_helper,drm_exec"). imagination/Kconfig
    # selects them from CONFIG_DRM_POWERVR=m so Kconfig pins them to =m; they
    # must ship as modules or powervr.ko fails with unknown symbols.
    for pat in ('drm_gpuvm*.ko', 'drm_exec*.ko', 'gpu-sched*.ko',
                'drm_shmem_helper*.ko', 'drm_kms_helper*.ko'):
        kos += sorted((S / 'lib/modules/7.3.0-rc2-dirty').glob(pat))
    # 2026-09-26 STALE-MODULE TRAP: stage/ keeps its own copies, so a rebuild
    # leaves stage/ stale and this script would ship the old .ko while still
    # printing MIRROR_OK. Fail closed instead (see stage-465g script).
    KDIR = Path('/home/host/kernel-trees/host-build/mainline-7.3')
    FRESH = {
        'powervr.ko': KDIR/'drivers/gpu/drm/imagination/powervr.ko',
        'aic8800_bsp.ko': KDIR/'drivers/net/wireless/aic8800/aic8800_bsp/aic8800_bsp.ko',
        'aic8800_fdrv.ko': KDIR/'drivers/net/wireless/aic8800/aic8800_fdrv/aic8800_fdrv.ko',
        'sunxi_rfkill.ko': KDIR/'drivers/misc/sunxi-rf/sunxi_rfkill.ko',
    }
    for name, built in FRESH.items():
        staged = S/'lib/modules/7.3.0-rc2-dirty'/name
        if built.is_file() and staged.is_file() and md5(built) != md5(staged):
            raise RuntimeError(
                f'STALE_STAGE {name}: build tree {md5(built)} != stage dir {md5(staged)}; '
                f'cp {built} {staged}, then re-run')
    names = {k.name for k in kos}
    for req in ('aic8800_fdrv.ko', 'aic8800_bsp.ko', 'sunxi_rfkill.ko', 'powervr.ko'):
        if req not in names:
            raise RuntimeError(f'missing required module {req}; found {sorted(names)}')
    # 2026-09-26: aic8800_bsp needs sunxi_wlan_* which live in sunxi_rfkill.ko,
    # so all three must ship together or the load order breaks.
    ssh(f'mkdir -p {REMOTE}/lib/modules/7.3.0-rc2-dirty\n')
    for ko in kos:
        scp(ko, REMOTE + '/lib/modules/7.3.0-rc2-dirty/' + ko.name)
        if vermagic(ko) != KVERMAGIC:
            raise RuntimeError(f'{ko.name} vermagic {vermagic(ko)} != kernel {KVERMAGIC}')
        print('MODULE_STAGE', ko.name, md5(ko), vermagic(ko))
    # 2026-09-26: ship the module index. Without modules.dep, `modprobe <mod>`
    # reports "Module not found" even with the .ko present, and nothing
    # autoloads. This mirror shipped no index at all until now.
    for idxname in ('modules.dep', 'modules.alias', 'modules.softdep',
                    'modules.load'):
        idx = S / 'lib/modules/7.3.0-rc2-dirty' / idxname
        if idx.is_file():
            scp(idx, REMOTE + '/lib/modules/7.3.0-rc2-dirty/' + idxname)
            print('MODULE_INDEX', idxname, md5(idx))
    fb = S / 'opiz3w-firstboot.sh'
    if fb.is_file():
        ssh(f'mkdir -p {REMOTE}/usr/local/sbin\n')
        scp(fb, REMOTE + '/usr/local/sbin/opiz3w-firstboot.sh')
        print('FIRSTBOOT', fb.name, md5(fb))
    print('KERNEL_VERMAGIC', KVERMAGIC)
    up = ssh(f'md5sum {REMOTE}/boot.scr {REMOTE}/boot/mainline/Image {REMOTE}/boot/mainline/sun60i-a733-orangepi-zero3w.dtb\n')
    print(up.stdout.strip())
    for n, h in want.items():
        if h not in up.stdout:
            raise RuntimeError(f'upload mismatch {n}')

    body = f'''set -eu
KREL='{KREL}'
if findmnt -n /mnt/sd >/dev/null 2>&1; then umount /mnt/sd; fi
mount {shlex.quote(card + '1')} /mnt/sd
trap 'umount /mnt/sd >/dev/null 2>&1 || true' EXIT
# 2026-09-27: the tab often has /mnt/sd stale-mounted to its own vfat EFI
# partition, and that shows "EFI" no matter what you mount over it - so a
# successful-looking mount can be the WRONG filesystem entirely. That made this
# script print MIRROR_OK after writing nothing useful. Verify we are on the
# ext4 partition of the card we were told to write, and fail closed otherwise.
MOUNTED_SRC=$(findmnt -n -o SOURCE /mnt/sd)
case "$MOUNTED_SRC" in
  {shlex.quote(card + '1')}) ;;
  *) echo "WRONG_MOUNT: /mnt/sd is $MOUNTED_SRC, expected {shlex.quote(card + '1')}"; exit 4 ;;
esac
[ "$(findmnt -n -o FSTYPE /mnt/sd)" = "ext4" ] || {{ echo "WRONG_FSTYPE: $(findmnt -n -o FSTYPE /mnt/sd)"; exit 4; }}
[ -d /mnt/sd/boot/mainline ] || {{ echo NO_BOOTDIR; exit 3; }}
[ -f /mnt/sd/boot.scr ]
mkdir -p /mnt/sd/boot/mainline
cp -a /mnt/sd/boot.scr /mnt/sd/boot.scr.bak-mirror-{stamp} 2>/dev/null || true
cp -a /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/Image.bak-mirror-{stamp} 2>/dev/null || true
cp -a /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb.bak-mirror-{stamp} 2>/dev/null || true
install -m 0644 {REMOTE}/boot.scr /mnt/sd/boot.scr
install -m 0644 {REMOTE}/boot/mainline/Image /mnt/sd/boot/mainline/Image
install -m 0644 {REMOTE}/boot/mainline/sun60i-a733-orangepi-zero3w.dtb /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
# 2026-09-26: install the aic8800 modules into BOTH dir names. modprobe resolves
# /lib/modules/$(uname -r), and this build's release is the git-describe string,
# not the plain 7.3.0-rc2-dirty.
for f in {REMOTE}/lib/modules/7.3.0-rc2-dirty/aic8800*.ko {REMOTE}/lib/modules/7.3.0-rc2-dirty/sunxi_rfkill*.ko {REMOTE}/lib/modules/7.3.0-rc2-dirty/powervr*.ko {REMOTE}/lib/modules/7.3.0-rc2-dirty/drm_gpuvm*.ko {REMOTE}/lib/modules/7.3.0-rc2-dirty/drm_exec*.ko {REMOTE}/lib/modules/7.3.0-rc2-dirty/drm_kms_helper*.ko {REMOTE}/lib/modules/7.3.0-rc2-dirty/drm_shmem_helper*.ko {REMOTE}/lib/modules/7.3.0-rc2-dirty/gpu-sched*.ko; do
  [ -f "$f" ] || continue
  for dest in /mnt/sd/lib/modules/7.3.0-rc2-dirty /mnt/sd/lib/modules/{KVERMAGIC}; do
    mkdir -p "$dest"; install -m 0644 "$f" "$dest/"
  done
done
# 2026-09-26: install the module index and the first-boot helper. Without
# modules.dep, `modprobe <mod>` says "Module not found" even with the .ko
# present, and nothing autoloads. Drop any stale .bin index too: modprobe
# prefers modules.dep.bin over the text file.
for f in {REMOTE}/lib/modules/7.3.0-rc2-dirty/modules.dep \
         {REMOTE}/lib/modules/7.3.0-rc2-dirty/modules.alias \
         {REMOTE}/lib/modules/7.3.0-rc2-dirty/modules.softdep \
         {REMOTE}/lib/modules/7.3.0-rc2-dirty/modules.load; do
  [ -f "$f" ] || continue
  for dest in "/mnt/sd/lib/modules/{KREL}" /mnt/sd/lib/modules/7.3.0-rc2-dirty; do
    mkdir -p "$dest"
    rm -f "$dest"/modules.dep.bin "$dest"/modules.alias.bin
    install -m 0644 "$f" "$dest/"
  done
done
# Autoload unit so the modules come up on boot without manual insmod.
if [ -f {REMOTE}/usr/local/sbin/opiz3w-firstboot.sh ]; then
  mkdir -p /mnt/sd/usr/local/sbin /mnt/sd/etc/systemd/system/multi-user.target.wants
  install -m 0755 {REMOTE}/usr/local/sbin/opiz3w-firstboot.sh /mnt/sd/usr/local/sbin/
  cat > /mnt/sd/etc/systemd/system/opiz3w-modules.service << 'UNIT'
[Unit]
Description=opiz3w module autoload (aic8800 WiFi + PowerVR GPU)
After=systemd-modules-load.service local-fs.target
Wants=network.target
[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=20
TimeoutStopSec=10
ExecStart=/usr/local/sbin/opiz3w-firstboot.sh
[Install]
WantedBy=multi-user.target
UNIT
  # 2026-09-26: leave autoload DISABLED. aic8800_bsp can block forever during
  # insmod, freezing the boot at ~17.9s with no getty. Load by hand instead.
  # ln -sf /etc/systemd/system/opiz3w-modules.service \
  #   /mnt/sd/etc/systemd/system/multi-user.target.wants/opiz3w-modules.service
  rm -f /mnt/sd/etc/systemd/system/multi-user.target.wants/opiz3w-modules.service
  rm -f /mnt/sd/etc/systemd/system/multi-user.target.wants/systemd-networkd-wait-online.service
  cat > /mnt/sd/etc/systemd/system/systemd-networkd-wait-online.service << 'MASKUNIT'
[Unit]
Description=disabled on opiz3w: this board has no physical Ethernet

[Service]
Type=oneshot
ExecStart=/bin/true
ExecStop=/bin/true
RemainAfterExit=yes
MASKUNIT
fi
# 2026-09-26: aic8800 firmware. Without it the driver dies on -ENOENT at
# request_firmware("aic8800d80/aic_userconfig_8800d80.txt").
if [ -d {REMOTE}/lib/firmware/powervr ]; then
  mkdir -p /mnt/sd/lib/firmware/powervr
  install -m 0644 {REMOTE}/lib/firmware/powervr/* /mnt/sd/lib/firmware/powervr/
fi
if [ -d {REMOTE}/lib/firmware/aic8800d80 ]; then
  mkdir -p /mnt/sd/lib/firmware/aic8800d80
  for f in {REMOTE}/lib/firmware/aic8800d80/*; do
    [ -f "$f" ] || continue
    install -m 0644 "$f" /mnt/sd/lib/firmware/aic8800d80/
  done
  cp -a {REMOTE}/lib/firmware/aic8800d80/aic_userconfig.txt /mnt/sd/lib/firmware/aic8800d80/aic_userconfig_8800d80.txt 2>/dev/null || true
fi
sync
md5sum /mnt/sd/boot.scr /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
printf 'ROOTFS\\n'
ls /mnt/sd | head -30
[ -e /mnt/sd/sbin/init ] && echo HAS_SBIN_INIT || echo NO_SBIN_INIT
sync
'''
    res = ssh("printf '%s\\n' 1 | sudo -S -p '' sh -c " + shlex.quote(body), timeout=120)
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        raise RuntimeError('aside mutation failed')
    for n, h in want.items():
        if h not in res.stdout:
            raise RuntimeError(f'card readback mismatch {n}')
    print('MIRROR_OK', stamp)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('MIRROR_ABORT', exc, file=sys.stderr)
        raise
