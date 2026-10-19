#!/bin/bash
# /home/host/opikernel/stage/board-recovery/push-safe-dtb.sh
# When board is up: replace the bricked DTB with the safe one + reboot.
# Replaces /boot/mainline/sun60i-a733-orangepi-zero3w.dtb
set -e
SAFE_DTB="$(dirname "$0")/safe-dtb.dtb"
ON_CARD="/boot/mainline/sun60i-a733-orangepi-zero3w.dtb"
HOST="orangepi@192.168.0.151"

[ -f "$SAFE_DTB" ] || { echo "no $SAFE_DTB"; exit 1; }

# Back up the broken DTB on the card
echo "==> backing up current $ON_CARD on board"
ssh -o ConnectTimeout=5 "$HOST" -- "sudo cp $ON_CARD ${ON_CARD}.bak-$(date +%Y%m%d-%H%M)" || true
echo "==> pushing safe DTB"
scp "$SAFE_DTB" "$HOST:/tmp/safe-dtb.dtb" || { echo "scp failed"; exit 1; }
echo "==> installing on card"
ssh "$HOST" -- "sudo cp /tmp/safe-dtb.dtb $ON_CARD && sudo rm /tmp/safe-dtb.dtb && sync"
echo "==> done. next boot will use the safe DTB."
echo "==> optionally: ssh $HOST -- 'sudo reboot' to test"
