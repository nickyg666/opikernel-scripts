#!/bin/bash
# tr-deploy-dtb2.sh — target dtb is root:root 755; stage via temp name then privileged swap.
set -u
H=/home/host/opikernel
SRC=$H/stage/7.3-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
D=/mnt/sd/boot/mainline
DST=$D/sun60i-a733-orangepi-zero3w.dtb
NEW=$D/sun60i-a733-orangepi-zero3w.dtb.new
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 tab@192.168.0.149"
WANT=$(md5sum "$SRC" | cut -d' ' -f1)

echo "=== push to temp name ==="
cat "$SRC" | timeout 60 $SSH "cat > $NEW" 2>&1 | grep -v Warning
echo "=== verify temp md5 (want $WANT) ==="
timeout 40 $SSH "md5sum $NEW; ls -l $NEW" 2>&1 | grep -v Warning

echo "=== privileged swap ==="
timeout 40 $SSH "echo 1 | sudo -S rm -f $DST 2>/dev/null; mv $NEW $DST; sync; ls -l --time-style=+%m-%d_%H:%M:%S $DST" 2>&1 | grep -v Warning

echo "=== FINAL card md5 ==="
timeout 40 $SSH "md5sum $DST" 2>&1 | grep -v Warning
