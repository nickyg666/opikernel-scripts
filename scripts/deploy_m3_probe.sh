#!/bin/bash
# deploy_m3_probe.sh — M3 RENDER-context EINVAL hunt
# Pushes instrumented powervr.ko (PVRDBG/PVRCTX) + cross-built probe to board .151,
# swaps module, runs probe, captures kernel prints, restores clean module.
# Host-side. Board must be reachable via SSH.
set -u
BOARD=orangepi@192.168.0.151
STAGE=/home/host/opikernel/stage/m3-instrumented
MOD_M3DBG=$STAGE/powervr.ko.m3dbg
PROBE=$STAGE/pvr_m3_probe
BOARD_WORK=/home/orangepi/pvrgl-work
MOD_CLEAN=/home/orangepi/kernel-backup-20260823/powervr.ko.orig

echo "== board reachability =="
ssh -F /dev/null -o ConnectTimeout=6 -o StrictHostKeyChecking=no "$BOARD" 'uptime' || { echo "BOARD UNREACHABLE — nothing done"; exit 1; }

echo "== pre-flight: running module md5 (expect a7105e42 clean) =="
ssh -F /dev/null "$BOARD" 'echo orangepi | sudo -S sh -c "MP=\$(find /lib/modules/\$(uname -r) -name powervr.ko 2>/dev/null | head -1); echo MODPATH=\$MP; md5sum \$MP"' 2>&1 | tail -3

echo "== pushing files =="
cat "$MOD_M3DBG" | ssh -F /dev/null "$BOARD" "cat > $BOARD_WORK/powervr.ko.m3dbg && md5sum $BOARD_WORK/powervr.ko.m3dbg"
cat "$PROBE" | ssh -F /dev/null "$BOARD" "cat > $BOARD_WORK/pvr_m3_probe && chmod +x $BOARD_WORK/pvr_m3_probe && md5sum $BOARD_WORK/pvr_m3_probe"

echo "== module swap + probe (board side) =="
ssh -F /dev/null "$BOARD" "echo orangepi | sudo -S sh -c '
set -x
lsmod | grep powervr
rmmod powervr 2>/dev/null || echo rmmod-failed
insmod $BOARD_WORK/powervr.ko.m3dbg && echo INSMOD-OK || echo INSMOD-FAIL
lsmod | grep powervr
dmesg -c > /dev/null 2>&1
echo ===PROBE-RUN===
$BOARD_WORK/pvr_m3_probe
echo ===PROBE-DONE===
echo ===KERNEL-LOG===
dmesg | grep -E \"PVRDBG|PVRCTX|powervr\" | tail -60
echo ===LOG-END===
rmmod powervr 2>/dev/null || true
RP=\$(find /lib/modules/\$(uname -r) -name powervr.ko 2>/dev/null | head -1)
insmod $RP && echo "RESTORE-OK md5=$(md5sum $RP | cut -d' ' -f1)" || { echo RESTORE-FAIL-trying-backup; insmod $MOD_CLEAN 2>/dev/null && echo RESTORE-OK-backup || echo RESTORE-FAIL-BOTH; }
lsmod | grep powervr
'" 2>&1 | tail -80

echo "== done =="
