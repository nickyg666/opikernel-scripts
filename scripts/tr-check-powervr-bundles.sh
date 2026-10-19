#!/usr/bin/env bash
# TelegramRunner: exact contents of the only bundle carrying module+firmware, plus module/fw identity.
cd /home/host/opikernel/stage/7.3-stage/deploy-va39 || exit 1
echo "=== modules-small-fixed-73e6dac2.tar.gz : powervr + firmware entries ==="
tar tzvf modules-small-fixed-73e6dac2.tar.gz 2>/dev/null | grep -E 'powervr|rogue_' | awk '{print $3, $4, $5, $6, $NF}'
echo "=== md5 of module candidates ==="
md5sum /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/powervr.ko \
       /home/host/opikernel/stage/7.3-stage/rootfs-overlay/lib/modules/7.3.0-rc2-dirty/kernel/drivers/gpu/drm/imagination/powervr.ko \
       /home/host/opikernel/stage/7.3-stage/deploy-va39/small/powervr.ko 2>/dev/null
echo "=== firmware identity ==="
md5sum /home/host/opikernel/stage/7.3-stage/lib/firmware/powervr/*.fw 2>/dev/null
echo "=== vermagic of staged module ==="
modinfo /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/powervr.ko 2>/dev/null | grep -E 'vermagic|filename'
