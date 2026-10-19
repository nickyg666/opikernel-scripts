#!/bin/bash
# ccu-enable-and-probe — the CCU unlock, serialized behind the KDIR build lock.
#
# Why: DTB needs four clock providers the build never produced.
#   ccu@2002000        allwinner,sun60iw2-ccu        -> gated by `# CONFIG_SUN60IW2_CCU is not set`
#   r_ccu@7010000      allwinner,sun60iw2-r-ccu      -> source present, NO Makefile rule (orphan)
#   rtc_ccu@7090000    allwinner,sun60iw2-rtc-ccu    -> wired
#   cpupll_ccu@8870000 allwinner,sun60iw2-cpupll     -> wired
# Without ccu@2002000, pinctrl@2000000 can't get its "apb" clock
# (pinctrl-sunxi.c:1703 devm_clk_get_enabled(...,"apb")) -> MMC/uart pin suppliers never resolve.
# Without r_ccu@7010000, pinctrl@7025000 can't get <0x27 0x01> "apb" -> s_twi0 (i2c@7083000) never
# probes -> AXP pmu@36 never probes -> dcdc1/bldo1 absent -> mmc@4020000 defers -> root never mounts.
#
# This script: waits for the lock, lands the config, verifies enablement, then does a
# fast targeted object build so we get the real compile errors in seconds instead of
# discovering them an hour into a full Image build. Releases the lock, then (if clean)
# launches the full Image+dtbs build through the sanctioned wrapper.
set -u
KDIR=/home/host/kernel-trees/host-build/mainline-7.3
CROSS=aarch64-linux-gnu-
LOCK=/tmp/kdir-7.3.build.lock
GOLD=/home/host/opikernel/stage/7.3-stage/.config-73-gold-ccu-enabled-20260918
LOG=/home/host/opikernel/logs/ccu-enable-and-probe.log
mkdir -p "$(dirname "$LOG")" /tmp/kdir-probe
exec >>"$LOG" 2>&1
echo "=== ccu-enable-and-probe start $(date '+%F %T') pid=$$ ==="
exec 9>"$LOCK"
echo "waiting for flock $LOCK (blocking, serialized with kdir-build.sh)..."
flock 9
echo "flock acquired $(date '+%F %T')"
if ps -eo cmd | grep -q '[m]ake ARCH=arm64'; then
  echo "ABORT: a make is still in the tree"; exit 1
fi
cd "$KDIR" || { echo "ABORT: no KDIR"; exit 1; }
cp -a .config "/tmp/kdir-config.bak-preccu-$(date +%Y%m%d-%H%M%S)"
cp "$GOLD" .config
echo "--- gold applied: $(md5sum "$GOLD")"
make ARCH=arm64 CROSS_COMPILE=$CROSS olddefconfig
echo "--- olddefconfig rc=$?"
echo "--- post-olddefconfig gate:"
grep -nE '^CONFIG_SUN60IW2_CCU|^CONFIG_ARCH_SUNXI=|^CONFIG_ARM64_VA_BITS=|^CONFIG_EFI_STUB|^CONFIG_PINCTRL_SUN60IW2' .config
grep -q '^CONFIG_SUN60IW2_CCU=y' .config && echo "GATE PASS: SUN60IW2_CCU=y" || echo "GATE FAIL: SUN60IW2_CCU not =y"
echo "--- Makefile r-ccu wiring:"
grep -n 'sun60iw2' drivers/clk/sunxi-ng/Makefile
echo "=== targeted CCU probe build $(date '+%F %T') ==="
nice -n 10 make ARCH=arm64 CROSS_COMPILE=$CROSS -j4 drivers/clk/sunxi-ng/sun60iw2-ccu.o > /tmp/kdir-probe/ccu.log 2>&1
rc=$?
echo "PROBE_EXIT=$rc errors=$(grep -c 'error:' /tmp/kdir-probe/ccu.log) warnings=$(grep -c 'warning:' /tmp/kdir-probe/ccu.log)"
echo "--- probe errors (first 60):"
grep -E 'error:' /tmp/kdir-probe/ccu.log | head -60
echo "--- probe tail:"
tail -25 /tmp/kdir-probe/ccu.log
ls -la drivers/clk/sunxi-ng/sun60iw2-ccu.o drivers/clk/sunxi-ng/ccu-sun60iw2-r.o 2>&1
exec 9>&-
echo "=== lock released $(date '+%F %T') ==="
if [ "$rc" -eq 0 ]; then
  echo "--- launching full Image+dtbs build through the sanctioned wrapper"
  JOBS=4 /home/host/opikernel/scripts/kdir-build.sh start Image dtbs
fi
echo "=== ccu-enable-and-probe done $(date '+%F %T') ==="
