#!/bin/bash
# Orange Pi Zero 3W Boot Fix Script
# Run this on the Pi after extracting the archive

set -e

BOOT_DIR="/boot"
DTB_DIR="${BOOT_DIR}/dtb-6.6.98-sun60iw2/allwinner"
OVERLAY_DIR="${DTB_DIR}/overlay"

echo "=== Orange Pi Zero 3W Boot Fix ==="

# Fix 1: Rename DTB file
if [ -f "${DTB_DIR}/sun60i-a733-orangepi-zero3w.dtb.new" ]; then
    echo "Renaming DTB file..."
    sudo mv "${DTB_DIR}/sun60i-a733-orangepi-zero3w.dtb.new" \
           "${DTB_DIR}/sun60i-a733-orangepi-zero3w-new.dtb"
    echo "Done."
else
    echo "DTB .dtb.new file not found (may already be fixed or different kernel version)"
fi

# Fix 2: Check overlay
echo "Checking current overlay..."
ls -la "${OVERLAY_DIR}/sun60i-a733-ili9486-spi.dtbo"

# Fix 3: Rebuild overlay if kernel source is available
if [ -d "/home/orangepi/linux-orangepi" ]; then
    echo "Rebuilding overlay..."
    cd /home/orangepi/linux-orangepi
    make dtbs DTC_FLAGS="-@" 2>/dev/null || echo "Make may have failed - check manually"
    sudo cp arch/arm64/boot/dts/allwinner/overlay/sun60i-a733-ili9486-spi.dtbo \
           "${OVERLAY_DIR}/"
fi

echo ""
echo "=== Verification Commands ==="
echo "After reboot, run:"
echo "  ls -la ${DTB_DIR}/sun60i-a733-orangepi-zero3w*.dtb"
echo "  dmesg | grep -i ili9486"
echo "  ls /dev/dri/"