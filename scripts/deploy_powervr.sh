#!/bin/bash
# deploy_powervr.sh — install decoder-only powervr.ko to the mainline module dir
# Usage: run ON BOARD as orangepi (sudo inside). Expects:
#   /opt/kernel-build/mainline-6.18/drivers/gpu/drm/imagination/powervr.ko  (fresh build)
set -e
SRC=/opt/kernel-build/mainline-6.18/drivers/gpu/drm/imagination/powervr.ko
DST=/lib/modules/6.18.19+/kernel/drivers/gpu/drm/imagination/powervr.ko
STAGE=/home/orangepi/pvrgl-work

if [ ! -f "$SRC" ]; then echo "FATAL: no $SRC"; exit 1; fi
SRC_MD5=$(md5sum "$SRC" | awk '{print $1}')
echo "src md5: $SRC_MD5"
echo "old md5: $(md5sum "$DST" | awk '{print $1}')"

# Back up whatever is currently installed (never destroy state)
if [ -f "$DST" ]; then
  cp -a "$DST" "$STAGE/powervr.ko.$(date +%Y%m%d-%H%M%S).bak"
  echo "backup -> $STAGE"
fi

# PVRDBG safety gate: refuse to deploy anything containing debug tags
if strings "$SRC" | grep -qE "PVRDBG|PVRCTX2|PVRSTEP"; then
  echo "FATAL: module contains PVRDBG/PVRCTX2/PVRSTEP strings — refusing deploy"
  exit 2
fi
echo "PVRDBG gate: clean"

# Install, sync, drop caches so the next md5 reads DISK not page cache
sudo cp "$SRC" "$DST"
sudo chmod 644 "$DST"
sync
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
sync
echo "installed md5: $(md5sum "$DST" | awk '{print $1}')"
echo "strings PVRDBG check: $(strings "$DST" | grep -c PVRDBG || true)"
echo "decoder present: $(strings "$DST" | grep -c 'FW context reset' || true)"
ls -la "$DST"
echo DEPLOY-OK
