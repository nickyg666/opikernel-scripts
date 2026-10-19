#!/bin/bash
# fsck + verify production card boot chain after unclean power-cut recovery
# Usage: bash /home/host/opikernel/scripts/fsck_verify_prod.sh <device> <mountpoint>
# e.g. bash fsck_verify_prod.sh /dev/sdh1 /mnt/prod
set -e
DEV="$1"
MNT="$2"
[ -z "$DEV" ] && { echo "usage: $0 <dev> <mnt>"; exit 1; }

echo "=== 1. Filesystem check (offline, read-only first) ==="
sudo e2fsck -fn "$DEV" || echo "WARN: e2fsck -fn exit $? (may be unclean shutdown remnants)"
echo "--- if errors found, run: sudo e2fsck -fy $DEV ---"

echo "=== 2. Mount rw ==="
sudo mkdir -p "$MNT"
sudo mount "$DEV" "$MNT" || { echo "MOUNT FAILED"; exit 1; }

echo "=== 3. Verify boot chain (md5 against host master) ==="
B="$MNT/boot"
echo "--- boot.scr ---"
md5sum "$B/boot.scr" 2>/dev/null | tee /tmp/fsck_bootscr.md5
echo "--- mainline/Image ---"
md5sum "$B/mainline/Image" 2>/dev/null | tee /tmp/fsck_image.md5
echo "--- mainline/tiny-uInitrd ---"
md5sum "$B/mainline/tiny-uInitrd" 2>/dev/null | tee /tmp/fsck_initrd.md5
echo "--- mainline DTB ---"
md5sum "$B/mainline/sun60i-a733-orangepi-zero3w.dtb" 2>/dev/null | tee /tmp/fsck_dtb.md5
echo "--- armed flag ---"
ls -la "$B/mainline/armed" 2>&1 || echo "MISSING armed"

echo "=== 4. Expected (master boot set) ==="
echo "boot.scr   bace60480887f41a3368779f240c7cf7"
echo "Image      beac4ac34c7caf1b11f1220f1ec63964 (26114056B)"
echo "tiny-uInitrd 06e5e6c6b1d2ec6c9e05c4711a5f1719 (1601510B)"
echo "DTB        bd5549062c3f302469cf119625aa6807 (213853B)"

echo "=== 5. env check ==="
grep -E "overlays|extraargs|rootdev|fdtfile" "$B/orangepiEnv.txt" 2>/dev/null || echo "no orangepiEnv.txt"

echo "=== 6. clean up ==="
sudo umount "$MNT" || echo "umount failed (still busy?)"
echo "DONE - card safe to eject"
