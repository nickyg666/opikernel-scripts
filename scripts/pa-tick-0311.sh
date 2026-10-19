#!/usr/bin/env bash
# PA bounded tick 03:11 — build identity + duplicate-claim audit (my lane)
set -u
T=/home/host/kernel-trees/host-build/mainline-7.3
echo "== 1) build alive? =="
pgrep -af 'kdir-build.sh|/usr/bin/make|^make ' | head -5
echo "-- lock:"; ls -l --time-style=+%m-%d_%H:%M:%S /tmp/kdir-7.3.build.lock 2>&1 | awk '{print $6,$7,$9}'
echo "-- log tail:"; tail -3 /tmp/kdir-build-Image-dtbs-modules.log 2>&1
echo "-- log size/mtime:"; ls -l --time-style=+%m-%d_%H:%M:%S /tmp/kdir-build-Image-dtbs-modules.log 2>&1 | awk '{print $5,$6,$7}'
echo "== 2) artifact identity =="
ls -l --time-style=+%m-%d_%H:%M:%S "$T/arch/arm64/boot/Image" "$T/vmlinux" 2>&1 | awk '{print $5,$6,$7,$9}'
md5sum "$T/arch/arm64/boot/Image" 2>&1
echo "-- newest pinctrl/dts source vs vmlinux:"
find "$T/drivers/pinctrl/sunxi" "$T/arch/arm64/boot/dts/allwinner" -newer "$T/vmlinux" -type f 2>/dev/null | head -5
echo "-- pinctrl-sunxi-bsp.c:"; ls -l --time-style=+%m-%d_%H:%M:%S "$T/drivers/pinctrl/sunxi/pinctrl-sunxi-bsp.c" 2>&1 | awk '{print $5,$6,$7,$9}'
echo "== 3) duplicate-claim audit (BACKLOG + role files) =="
B=/home/host/opikernel/agentic-pool/BACKLOG.md
grep -nE '^### |status: (open|claimed|in.progress|blocked)|claimed-by:' "$B" 2>/dev/null | head -40
echo "-- claims summary:"
grep -ho 'claimed-by:.*' "$B" 2>/dev/null | sort | uniq -c | sort -rn | head -10
echo "== 4) board/serial (read-only) =="
ls -l --time-style=+%m-%d_%H:%M:%S /home/host/opikernel/pvrgl-work/sercap_room_live.log 2>&1 | awk '{print $5,$6,$7}'
pgrep -af serial_single_owner.py | head -3
