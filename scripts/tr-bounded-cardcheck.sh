#!/bin/bash
# tr-bounded-cardcheck.sh — is the board SD in the tab reader? (unblocks flashing the staged fix without network)
echo "=== tab .149 ==="
ping -c1 -W2 192.168.0.149 2>&1 | tail -1
echo "=== board .151 ==="
ping -c1 -W2 192.168.0.151 2>&1 | tail -1
echo "=== tab block devices ==="
timeout 20 sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 tab@192.168.0.149 \
  "lsblk -o NAME,SIZE,LABEL,PARTUUID,MOUNTPOINT | grep -Ei 'sd|mmc'" 2>&1 | tail -12
echo "=== staged fix present on host ==="
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/opikernel/stage/7.3-stage/boot/mainline/Image /home/host/opikernel/stage/7.3-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb 2>&1
