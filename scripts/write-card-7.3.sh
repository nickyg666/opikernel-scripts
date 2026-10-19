#!/bin/bash
# write-card-7.3.sh — push the CURRENT 7.3 Image+DTB onto the opi_root card while it sits in the
# tab's onboard SD reader, with before/after md5 + magic readback and a dated backup in place.
#
# The card is NOT visible from .168 (board boots from its own microSD), so the only write path is:
#   Nick pulls the card from the board -> inserts it in tab (.149) reader -> this script -> back.
#
# Usage: scripts/write-card-7.3.sh [--dry-run]
# Refs: pvrgl-work/TR-EVIDENCE-20260920-1140-card-written-and-backup-blocked.md (proven 11:40 run)
set -euo pipefail
TAB=${TAB:-tab@192.168.0.149}
TABPW=${TABPW:-1}
KDIR=${KDIR:-/home/host/kernel-trees/host-build/mainline-7.3}
IMG=${IMG:-$KDIR/arch/arm64/boot/Image}
DTB=${DTB:-$KDIR/arch/arm64/boot/dts/allwinner/sun60i-a733-orangepi-zero3w.dtb}
MP=${MP:-/mnt/sdcard}
STAMP=$(date +%Y%m%d-%H%M%S)
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
SSH="sshpass -p $TABPW ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 $TAB"

[ -f "$IMG" ] && [ -f "$DTB" ] || { echo "REFUSED: missing $IMG or $DTB"; exit 1; }
IMD5=$(md5sum "$IMG" | cut -d' ' -f1); DMD5=$(md5sum "$DTB" | cut -d' ' -f1)
IMAGIC=$(head -c4 "$IMG" | xxd -p); DMAGIC=$(head -c4 "$DTB" | xxd -p)
echo "host: Image $(stat -c%s "$IMG") B md5=$IMD5 magic=$IMAGIC"
echo "host: DTB   $(stat -c%s "$DTB") B md5=$DMD5 magic=$DMAGIC"
[ "$IMAGIC" = "1f2003d5" ] || { echo "REFUSED: Image magic $IMAGIC"; exit 1; }
[ "$DMAGIC" = "d00dfeed" ] || { echo "REFUSED: DTB magic $DMAGIC"; exit 1; }

echo "--- tab: find the opi_root card ---"
$SSH 'lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT | grep -vE "loop|snap"'
DEV=$($SSH "lsblk -o NAME,LABEL,FSTYPE -P | awk -F'\"' '\$4==\"opi_root\"{print \$2}'" | head -1)
DEV=${DEV:-}
[ -n "$DEV" ] || { echo "NO CARD IN TAB READER (no LABEL=opi_root). Physical step required."; exit 2; }
echo "tab: card partition = /dev/$DEV"
$SSH "echo $TABPW | sudo -S umount /mnt/sd /mnt/sdprobe /mnt 2>/dev/null; mkdir -p $MP; mountpoint -q $MP || echo $TABPW | sudo -S mount /dev/$DEV $MP; df -h $MP | tail -1"
echo "--- tab: BEFORE ---"
$SSH "ls -l --time-style=+%m-%d_%H:%M:%S $MP/boot/mainline/Image $MP/boot/mainline/sun60i-a733-orangepi-zero3w.dtb; md5sum $MP/boot/mainline/Image $MP/boot/mainline/sun60i-a733-orangepi-zero3w.dtb"
[ "$DRY" = 1 ] && { echo "DRY-RUN: no write performed"; exit 0; }

echo "--- transfer host -> tab /tmp ---"
cat "$IMG" | $SSH "cat > /tmp/tr-Image-new" 
cat "$DTB" | $SSH "cat > /tmp/tr-dtb-new"
T1=$($SSH "md5sum /tmp/tr-Image-new | cut -d' ' -f1"); T2=$($SSH "md5sum /tmp/tr-dtb-new | cut -d' ' -f1")
[ "$T1" = "$IMD5" ] || { echo "REFUSED: transfer md5 mismatch Image $T1 != $IMD5"; exit 1; }
[ "$T2" = "$DMD5" ] || { echo "REFUSED: transfer md5 mismatch DTB $T2 != $DMD5"; exit 1; }
echo "transfer md5 OK ($T1 / $T2)"

echo "--- write to card (dated backups kept in place) ---"
$SSH "echo $TABPW | sudo -S cp -p $MP/boot/mainline/Image $MP/boot/mainline/Image.bak-trdb-$STAMP 2>/dev/null; \
      echo $TABPW | sudo -S cp -p $MP/boot/mainline/sun60i-a733-orangepi-zero3w.dtb $MP/boot/mainline/sun60i-a733-orangepi-zero3w.dtb.bak-trdb-$STAMP 2>/dev/null; \
      echo $TABPW | sudo -S cp /tmp/tr-Image-new $MP/boot/mainline/Image && \
      echo $TABPW | sudo -S cp /tmp/tr-dtb-new $MP/boot/mainline/sun60i-a733-orangepi-zero3w.dtb && sync"
echo "--- tab: AFTER (readback off the card) ---"
$SSH "md5sum $MP/boot/mainline/Image $MP/boot/mainline/sun60i-a733-orangepi-zero3w.dtb; \
      head -c4 $MP/boot/mainline/Image | xxd -p; head -c4 $MP/boot/mainline/sun60i-a733-orangepi-zero3w.dtb | xxd -p; \
      ls -l --time-style=+%m-%d_%H:%M:%S $MP/boot/mainline/ | head -8"
echo "--- unmount cleanly (safe to pull) ---"
$SSH "sync; echo $TABPW | sudo -S umount $MP && lsblk -o NAME,LABEL,MOUNTPOINT | grep -vE 'loop|snap'"
echo "expect Image md5 = $IMD5  DTB md5 = $DMD5"
