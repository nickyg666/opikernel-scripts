#!/bin/bash
# tr-bounded-stagecard.sh — does the tab's staging card already carry the pinctrl fix?
SSH="timeout 40 sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 tab@192.168.0.149"
echo "=== card /boot/mainline ==="
$SSH "ls -l --time-style=+%m-%d_%H:%M:%S /mnt/sd/boot/mainline/ 2>&1 | head -20" 2>&1 | tail -20
echo "=== card md5 Image/dtb ==="
$SSH "md5sum /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb 2>&1" 2>&1 | tail -4
echo "=== HOST staged md5 (target) ==="
md5sum /home/host/opikernel/stage/7.3-stage/boot/mainline/Image /home/host/opikernel/stage/7.3-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
