#!/bin/bash
# tr-verify-deployed.sh — prove the fix is inside the deployed DTB + boot.scr/Image consistency
cd /home/host/opikernel
SRC=stage/7.3-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
echo "=== pinctrl node in DEPLOYED dtb (md5-identical to card) ==="
dtc -I dtb -O dts "$SRC" 2>/dev/null | grep -A6 'pinctrl@2000000' | head -12
echo "=== interrupt-parent<>gic> count ==="
dtc -I dtb -O dts "$SRC" 2>/dev/null | grep -c 'interrupt-parent'
echo "=== card boot.scr + Image ==="
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 tab@192.168.0.149"
timeout 40 $SSH "ls -l --time-style=+%m-%d_%H:%M:%S /mnt/sd/boot/boot.scr /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb" 2>&1 | grep -v Warning
