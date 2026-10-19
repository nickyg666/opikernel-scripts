#!/bin/bash
# tr-deploy-dtb-to-stagecard.sh — staging card has FIXED Image but PRE-FIX DTB. Deploy staged DTB.
set -u
H=/home/host/opikernel
SRC=$H/stage/7.3-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
DST=/mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 tab@192.168.0.149"
TAG=$(date +%Y%m%d-%H%M)

echo "=== 1. backup pre-fix dtb on card ==="
timeout 40 $SSH "cp -v $DST $DST.bak-tr-$TAG && ls -l --time-style=+%m-%d_%H:%M:%S $DST.bak-tr-$TAG" 2>&1 | tail -3

echo "=== 2. push staged dtb (host -> card) ==="
cat "$SRC" | timeout 60 $SSH "cat > $DST" 2>&1 | tail -2
echo "push_rc=$?"

echo "=== 3. verify md5 on card ==="
timeout 40 $SSH "md5sum $DST; ls -l --time-style=+%m-%d_%H:%M:%S $DST; sync" 2>&1 | tail -3
echo "=== expected (host staged) ==="
md5sum "$SRC"
