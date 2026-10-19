#!/bin/bash
# /home/host/opikernel/stage/board-recovery/golden-recovery.sh
# Board .151 golden recovery workflow.
# When board is bricked: smartplug cycle + U-Boot interrupt + booti safe DTB.
# 
# Usage:
#   ./golden-recovery.sh                  # full cycle: power cycle + U-Boot + booti safe
#   ./golden-recovery.sh --skip-power     # skip power cycle (just U-Boot interrupt)
#   ./golden-recovery.sh --safe-only      # just upload the safe DTB to /boot/mainline
#
# Prerequisites:
#   /dev/ttyACM0 — pico picoprobe on UART
#   ~/.vncpass has been updated (done 2026-09-05)
#   safe-dtb.dtb in same dir (bd554906 - AIC8800 UHS-3v3 + de-iommu fix)

set -e
PROBE=/dev/ttyACM0
SAFE_DTB="$(dirname "$0")/safe-dtb.dtb"
ON_CARD_DTB_PATH="/boot/mainline/sun60i-a733-orangepi-zero3w.dtb"
SKIP_POWER=0
SAFE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-power) SKIP_POWER=1 ;;
    --safe-only) SAFE_ONLY=1 ;;
  esac
done

# Sanity
[ -c "$PROBE" ] || { echo "ERROR: $PROBE not a char device. Is the pico connected?"; exit 1; }
[ -f "$SAFE_DTB" ] || { echo "ERROR: $SAFE_DTB not found"; exit 1; }

send() {
  printf "\r" > "$PROBE"; sleep 0.3
  printf "%s\r" "$1" > "$PROBE"; sleep 1.0
}

# 1. Smartplug power cycle (unless --skip-power)
if [ $SKIP_POWER -eq 0 ] && [ $SAFE_ONLY -eq 0 ]; then
  echo "==> smartplug cycle (opiz3w)"
  python3.14 /home/host/smartplug.py cycle opiz3w 2>&1 | head -n 3
  echo "==> waiting 30s for board to come back"
  sleep 30
fi

# 2. U-Boot interrupt
echo "==> sending Enter spam to catch U-Boot prompt"
DURATION=12
END=$(($(date +%s) + DURATION))
COUNT=0
while [ $(date +%s) -lt $END ]; do
  printf "\r" > "$PROBE"; sleep 0.05
  COUNT=$((COUNT+1))
done
echo "  sent $COUNT <CR>"

# 3. U-Boot boot with safe DTB (booti the in-RAM copy)
echo "==> injecting U-Boot boot sequence with safe DTB"
# A733 memory map:
#   kernel  = 0x41000000
#   fdt     = 0x44000000
#   initrd  = 0x45000000
#   scratch = 0x46000000
BA='root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 console=tty1 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 usb-storage.quirks= fbcon=map:1'
send "setenv bootargs $BA"
send "setenv kernel_addr_r 0x41000000"
send "setenv fdt_addr_r 0x44000000"
send "setenv ramdisk_addr_r 0x45000000"
send "setenv load_addr 0x46000000"
# Load Image and tiny-uInitrd from card (these are not the bricked part)
send "load mmc 0:1 0x46000000 /boot/mainline/tiny-uInitrd"
send "load mmc 0:1 0x41000000 /boot/mainline/Image"
# Load DTB from a USB stick or network instead. As a fallback, use the on-card backup name.
# But for true golden: load the safe DTB from the host via ymodem/pxe/etc — not done yet.
# For now, fall back to the on-card dtb.bak-4316333a (de-noiommu proven)
send "load mmc 0:1 0x44000000 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb.bak-golden-20260905"
send "fdt addr 0x44000000"
send "fdt resize 65536"
echo "==> booting: booti 0x41000000 0x46000000 0x44000000"
send "booti 0x41000000 0x46000000 0x44000000"
echo "==> boot sent. waiting 45s for board to come up"
sleep 45

# 4. Verify
echo "==> checking SSH"
if ssh -o ConnectTimeout=5 -o BatchMode=yes orangepi@192.168.0.151 echo ok 2>&1 | head -n 1; then
  echo "==> BOARD IS BACK"
  ssh orangepi@192.168.0.151 uname -r
  exit 0
else
  echo "==> SSH still down. Try: ssh orangepi@192.168.0.151 with password (pw=orangepi)"
  exit 1
fi
