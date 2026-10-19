#!/usr/bin/env bash
# TelegramRunner: is the bundle's powervr.ko the same build as the newest staged one?
set -e
T=$(mktemp -d)
cd "$T"
tar xzf /home/host/opikernel/stage/7.3-stage/deploy-va39/modules-small-fixed-73e6dac2.tar.gz ./powervr.ko
echo "=== bundle powervr.ko ==="
ls -l --time-style=+%m-%d_%H:%M:%S powervr.ko
md5sum powervr.ko
modinfo ./powervr.ko | grep vermagic
echo "=== newest staged powervr.ko ==="
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/powervr.ko
md5sum /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/powervr.ko
echo "=== identical? ==="
if cmp -s powervr.ko /home/host/opikernel/stage/7.3-stage/lib/modules/7.3.0-rc2-dirty/powervr.ko; then echo "IDENTICAL"; else echo "DIFFERENT"; fi
rm -rf "$T"
