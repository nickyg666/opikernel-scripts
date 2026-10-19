#!/bin/bash
# offline_fsck.sh — RO-locked offline e2fsck for the REAL production card.
# Run on tab@192.168.0.149 AFTER Nick swaps the real card into the reader.
# Usage: bash offline_fsck.sh   (needs sudo; password 1)
set -u
REAL_UUID="442af407-cb84-48f8-845e-4be5cd18ce13"

echo "=== scanning for opi_root card ==="
DEV=""
for d in /dev/sd?; do
  uuid=$(sudo blkid -s UUID -o value ${d}1 2>/dev/null)
  if [ "$uuid" = "$REAL_UUID" ]; then
    DEV=$d
    echo "FOUND: $DEV (part1 UUID=$REAL_UUID)"
    break
  fi
done
if [ -z "$DEV" ]; then
  echo "REAL CARD NOT FOUND. Devices present:"
  sudo lsblk -o NAME,SIZE,LABEL,UUID,MOUNTPOINT | grep -E "sd|NAME" | head -12
  echo "Swap the real card into the tab reader, then rerun."
  exit 1
fi

echo "=== mounting? check ==="
mount | grep "$DEV" && { echo "WARNING: mounted — unmounting"; sudo umount ${DEV}?* 2>/dev/null; sudo umount $DEV 2>/dev/null; }

echo "=== RO-lock + fsck -f (5 passes, no write until clean) ==="
sudo blockdev --setro $DEV
sudo e2fsck -fn ${DEV}1 2>&1 | tail -25
echo "=== exit: $? (0 = clean, 1 = repaired, 4 = errors remain) ==="
echo "Run with -fy to auto-repair if errors were found."
