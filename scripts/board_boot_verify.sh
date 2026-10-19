#!/bin/bash
# board_boot_verify.sh — run ON the board after production card swap (or via ssh)
# Verifies the full boot set landed correctly: DTB props, kernel, WiFi, no panics.
# Usage: bash /home/orangepi/pvrgl-work/board_boot_verify.sh
echo "=== BOOT VERIFY $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "--- kernel ---"
uname -r
echo "--- uptime ---"
uptime
echo "--- DTB mmc2 max-frequency (expect 50000000 = 0x2faf080) ---"
cat /proc/device-tree/soc@3000000/sdmmc@4021000/max-frequency 2>/dev/null | od -An -tu4 | tr -d ' '
echo "--- DTB mmc0 vqmmc-supply phandle (expect 0x78 = 120) ---"
cat /proc/device-tree/soc@3000000/sdmmc@4020000/vqmmc-supply 2>/dev/null | od -An -tu4 | tr -d ' '
echo "--- de@5000000 iommus (expect EMPTY) ---"
ls /proc/device-tree/soc@3000000/display-engine@5000000/iommus 2>/dev/null && echo "IOMMUS PRESENT (BAD)" || echo "de iommus stripped (GOOD)"
echo "--- drm cards ---"
ls /dev/dri/ 2>/dev/null
echo "--- fb devices ---"
ls -la /dev/fb* 2>/dev/null
echo "--- powervr module ---"
lsmod | grep -E "powervr|pvr" || echo "powervr NOT loaded"
echo "--- aic8800 modules ---"
lsmod | grep aic || echo "aic8800 NOT loaded"
echo "--- wlan ---"
ip link show wlan0 2>/dev/null | head -3 || echo "wlan0 absent"
nmcli -t -f WIFI,STATE dev 2>/dev/null | head -5
echo "--- panics/oops in dmesg ---"
dmesg | grep -iE "panic|oops|BUG:|kernel fault|unable to handle" | head -20 || echo "clean dmesg"
echo "--- systemd failed units ---"
systemctl --failed --no-legend 2>/dev/null | head -10 || echo "systemctl unavailable"
echo "=== END BOOT VERIFY ==="
