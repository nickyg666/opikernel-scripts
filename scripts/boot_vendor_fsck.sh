#!/bin/bash
# boot_vendor_fsck.sh — at U-Boot prompt: vendor 6.6 boot with fsck.mode=force.
set -u
DEV=/dev/ttyACM0
LOG=/home/host/pvrgl-work/sercap_boot.log

sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1
sleep 1
sudo stty -F $DEV 115200 raw -echo
(sudo setsid bash -c "exec cat $DEV >> $LOG" >/dev/null 2>&1 &)
sleep 1

feed() {
  printf "%s\n" "$1" | sudo tee $DEV >/dev/null 2>&1
  sleep 1
}

feed ""
sleep 1
feed "setenv bootargs 'root=/dev/mmcblk1p1 rootwait fsck.mode=force fsck.repair=yes console=ttyS0,115200 loglevel=7'"
feed "load mmc 0:1 41000000 boot/uImage"
feed "load mmc 0:1 43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb"
feed "fdt addr 43000000"
feed "fdt resize 65536"
feed "bootm 41000000 - 43000000"
echo "sent; watching..."
sleep 5
tail -c 1000 $LOG | grep -a . | tail -8
