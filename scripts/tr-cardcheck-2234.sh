#!/bin/bash
# TR bounded action 22:34 — verify the staging card in tab reader still holds the FIXED dtb+Image.
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 tab@192.168.0.149"
$SSH 'lsblk -o NAME,SIZE,FSTYPE,LABEL,PARTUUID,MOUNTPOINT | head -20; echo "---"; ls -l --time-style=+%m-%d_%H:%M:%S /mnt/sd/boot/mainline/ 2>/dev/null'
echo "=== MD5 ON CARD ==="
$SSH 'sudo -S md5sum /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb 2>/dev/null <<< 1'
echo "=== BOOT.SCR ==="
$SSH 'sudo -S ls -l --time-style=+%m-%d_%H:%M:%S /mnt/sd/boot/boot.scr 2>/dev/null <<< 1'
