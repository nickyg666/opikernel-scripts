#!/usr/bin/env bash
# card-repair.sh — run AFTER the corrupted board card is mounted on tab .149 (/mnt/sd)
# Usage (from host): ssh tab@192.168.0.149 'sudo bash -s' < card-repair.sh
set -euo pipefail
SD=/mnt/sd
echo "== fsck =="
sudo fsck -y /dev/sda1 || true
echo "== free space =="
df -h $SD
echo "== clean boot files =="
sudo rm -f $SD/boot.scr $SD/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
echo "== restore from host (scp from .168 next step) =="
