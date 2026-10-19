#!/usr/bin/env python3
"""Stage the A733 regulator-fixed artifacts onto exactly one 465G card in tab.

Fail-closed: physical size must identify one 465G candidate, the 32G card cannot
be selected, uploads must hash-match, card writes run as root, and readback must
match before the script reports success.
"""
import hashlib
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/home/host/opikernel')
K = Path('/home/host/kernel-trees/host-build/mainline-7.3')
STAGE = ROOT / 'stage/7.3-stage'
TAB = 'tab@192.168.0.149'
REMOTE = '/tmp/opiz3w-stage'
IMAGE_MD5 = '5dc5f3d2f885a1c1fee6a768dac2f234'
DTB_MD5 = '37b7a6bdb99bbdf67cd8a81b6a8eaa47'
BOOT_MD5 = 'a03b4451474d9bb47f292ec3c05c7d2d'


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def ssh_sh(script, timeout=60):
    args = [
        'sshpass', '-p', '1', 'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'ConnectTimeout=8', TAB, 'sh -s',
    ]
    return subprocess.run(args, input=script, text=True,
                          capture_output=True, timeout=timeout)


def scp(local, remote):
    args = [
        'sshpass', '-p', '1', 'scp', '-q',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null', str(local), TAB + ':' + remote,
    ]
    subprocess.run(args, text=True, check=True, timeout=120)


def require_file_hash(path, expected, size=None, magic=None):
    data = path.read_bytes()
    got = hashlib.md5(data).hexdigest()
    if got != expected:
        raise RuntimeError(f'hash mismatch {path}: {got}')
    if size is not None and len(data) != size:
        raise RuntimeError(f'size mismatch {path}: {len(data)} != {size}')
    if magic is not None and data[:4] != magic:
        raise RuntimeError(f'magic mismatch {path}: {data[:4].hex()}')
    return got


def main():
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    source_image = K / 'arch/arm64/boot/Image'
    source_dtb = K / 'arch/arm64/boot/dts/allwinner/sun60i-a733-orangepi-zero3w.dtb'
    boot = STAGE / 'boot.scr'

    require_file_hash(source_image, IMAGE_MD5, 41707528, bytes.fromhex('1f2003d5'))
    require_file_hash(source_dtb, DTB_MD5, 207607, bytes.fromhex('d00dfeed'))
    require_file_hash(boot, BOOT_MD5, 464)

    # Back up and update only host staging; never silently overwrite evidence.
    for src, name in ((source_image, 'Image'), (source_dtb, 'sun60i-a733-orangepi-zero3w.dtb')):
        dst = STAGE / 'boot/mainline' / name
        if dst.exists():
            backup = dst.with_name(dst.name + '.bak-axp8191-reg-' + stamp)
            shutil.copy2(dst, backup)
            print('HOST_BACKUP', backup, md5(backup))
        shutil.copy2(src, dst)
        print('HOST_STAGE', dst, md5(dst))

    preflight_script = r'''set -eu
CAND=
COUNT=0
for dev in /dev/sda /dev/sdb; do
  if [ -b "$dev" ]; then
    size=$(lsblk -b -dn -o SIZE "$dev" 2>/dev/null | tr -d '[:space:]' || true)
    case "$size" in
      ''|*[!0-9]*) continue ;;
    esac
    if [ "$size" -ge 450000000000 ]; then
      CAND="$dev"
      COUNT=$((COUNT + 1))
    fi
  fi
done
[ "$COUNT" -eq 1 ] || { echo "NO_UNIQUE_465G COUNT=$COUNT"; exit 2; }
[ -b "$CAND"1 ] || { echo "NO_PARTITION $CAND"; exit 2; }
fstype=$(lsblk -no FSTYPE "$CAND"1 2>/dev/null | tr -d '[:space:]' || true)
part=$(lsblk -no PARTUUID "$CAND"1 2>/dev/null | tr -d '[:space:]' || true)
echo "PREFLIGHT_OK CARD=$CAND SIZE=$size FSTYPE=$fstype PARTUUID=$part"
'''
    pre = ssh_sh(preflight_script)
    if pre.returncode != 0:
        print(pre.stdout, end='')
        print(pre.stderr, file=sys.stderr, end='')
        raise RuntimeError('tab 465G preflight failed')
    pre_text = pre.stdout.strip()
    print('TAB_PREFLIGHT\n' + pre_text)
    card = None
    for line in pre_text.splitlines():
        if line.startswith('PREFLIGHT_OK CARD='):
            card = line.split('CARD=', 1)[1].split(' ', 1)[0]
    if card not in ('/dev/sda', '/dev/sdb'):
        raise RuntimeError('preflight did not return a safe card device')

    # Upload to tab /tmp, never directly to a card device.
    prep = ssh_sh('mkdir -p /tmp/opiz3w-stage/boot/mainline\n')
    if prep.returncode != 0:
        print(prep.stderr, file=sys.stderr, end='')
        raise RuntimeError('tab upload directory failed')
    scp(source_image, REMOTE + '/boot/mainline/Image')
    scp(source_dtb, REMOTE + '/boot/mainline/sun60i-a733-orangepi-zero3w.dtb')
    scp(boot, REMOTE + '/boot.scr')
    verify = ssh_sh(
        'md5sum /tmp/opiz3w-stage/boot.scr '
        '/tmp/opiz3w-stage/boot/mainline/Image '
        '/tmp/opiz3w-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb\n'
    )
    if verify.returncode != 0:
        print(verify.stderr, file=sys.stderr, end='')
        raise RuntimeError('tab upload verification failed')
    print('TAB_UPLOAD_VERIFY\n' + verify.stdout.strip())
    for want in (BOOT_MD5, IMAGE_MD5, DTB_MD5):
        if want not in verify.stdout:
            raise RuntimeError('tab upload hash mismatch')

    privileged_body = f'''set -eu
mount {shlex.quote(card + '1')} /mnt/sd
trap 'umount /mnt/sd >/dev/null 2>&1 || true' EXIT
[ -f /mnt/sd/boot.scr ]
[ -f /mnt/sd/boot/mainline/Image ]
[ -f /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb ]
cp -a /mnt/sd/boot.scr /mnt/sd/boot.scr.bak-axp8191-reg-{stamp}
cp -a /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/Image.bak-axp8191-reg-{stamp}
cp -a /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb.bak-axp8191-reg-{stamp}
install -m 0644 /tmp/opiz3w-stage/boot.scr /mnt/sd/boot.scr
install -m 0644 /tmp/opiz3w-stage/boot/mainline/Image /mnt/sd/boot/mainline/Image
install -m 0644 /tmp/opiz3w-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
sync
md5sum /mnt/sd/boot.scr /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
sync
'''
    mutation_script = r'''set -eu
if ! sudo -n true 2>/dev/null; then
  printf '%s\n' 1 | sudo -S -p '' -v
fi
sudo -n sh -c ''' + shlex.quote(privileged_body) + r'''
'''
    mutation = ssh_sh(mutation_script, timeout=90)
    if mutation.returncode != 0:
        print(mutation.stdout, end='')
        print(mutation.stderr, file=sys.stderr, end='')
        raise RuntimeError('tab card mutation failed')
    result = mutation.stdout.strip()
    print('TAB_CARD_RESULT\n' + result)
    for want in (BOOT_MD5, IMAGE_MD5, DTB_MD5):
        if want not in result:
            raise RuntimeError('card readback hash mismatch')
    print('STAGED_OK', stamp)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('STAGING_ABORT', type(exc).__name__, str(exc), file=sys.stderr)
        raise
