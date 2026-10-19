#!/bin/bash
# serial_fsck_rescue.sh — U-Boot vendor-boot rescue with fsck.mode=force.
# Usage: sudo bash serial_fsck_rescue.sh
# Requires: pico serial bridge on /dev/ttyACM0 (host), board on Wyze plug.
set -u
DEV=/dev/ttyACM0
LOG=/home/host/pvrgl-work/sercap2.log
CAP=/home/host/pvrgl-work/sercap_rescue.log

# 1. Make sure nothing else holds the port.
sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1
sleep 1

# 2. Start a fresh capture (append).
(sudo setsid bash -c "exec cat $DEV >> $CAP" >/dev/null 2>&1 &)
sleep 1

# 3. Power cycle the board.
python3 /home/host/smartplug.py reboot >/dev/null 2>&1
echo "Power cycled; entering U-Boot..."

# 4. Enter-spam to catch the autoboot window (start ~2.5s after power-on).
sleep 2.5
for i in $(seq 1 44); do
  printf "\n" | sudo tee $DEV >/dev/null 2>&1
  sleep 0.25
done

# 5. Feed rescue commands one per line, paced.
feed() {
  printf "%s\n" "$1" | sudo tee $DEV >/dev/null 2>&1
  sleep 0.8
}

sleep 1
feed "setenv bootargs 'root=/dev/mmcblk1p1 rootwait fsck.mode=force fsck.repair=yes console=ttyS0,115200 loglevel=7'"
feed "load mmc 0:1 41000000 boot/uImage"
feed "load mmc 0:1 43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb"
feed "fdt addr 43000000"
feed "fdt resize 65536"
feed "bootm 41000000 - 43000000"

echo "Rescue boot commands sent. Watch $CAP for fsck + boot progress."
