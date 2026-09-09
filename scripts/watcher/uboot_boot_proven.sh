#!/bin/bash
# Proven working boot: vendor kernel 6.6.98 + NO initrd (built into uImage)
# Source: sercap_vendor_repair.log (full userspace achieved)
# Key: bootm 41000000 - 43000000  ← NO initrd arg!

# Serial console: picoprobe on host side
D=/dev/ttyACM0
LOG=/home/host/pvrgl-work/boot_vendor_working.log

send(){
  printf "\r" > $D
  sleep 0.4
  printf "%s\r" "$1" > $D
  sleep 1.3
}

bootargs='root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm'

{
  echo "[$(date '+%H:%M:%S')] === VENDOR KERNEL PROVEN BOOT ==="
  echo "[$(date '+%H:%M:%S')] Killing readers..."
  kill $(cat /tmp/ser_reader.pid 2>/dev/null) 2>/dev/null
  sleep 1

  echo "[$(date '+%H:%M:%S')] Starting serial reader in background..."
  cat $D > $LOG &
  echo $! > /tmp/ser_reader.pid
  sleep 1

  echo "[$(date '+%H:%M:%S')] Power cycling..."
  python3 /home/host/smartplug.py off 2>/dev/null
  sleep 3
  python3 /home/host/smartplug.py on 2>/dev/null
  echo "[$(date '+%H:%M:%S')] Waiting for U-Boot..."
} >> $LOG 2>&1

sleep 12

{
  echo "[$(date '+%H:%M:%S')] Interrupting autoboot..."
  send ""
  sleep 3

  echo "[$(date '+%H:%M:%S')] Setting bootargs..."
  send "setenv bootargs $bootargs"

  echo "[$(date '+%H:%M:%S')] Loading vendor kernel uImage at 0x41000000..."
  send "load mmc 0:1 0x41000000 boot/uImage"

  echo "[$(date '+%H:%M:%S')] Loading vendor DTB at 0x43000000..."
  send "load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb"

  echo "[$(date '+%H:%M:%S')] Booting NO INITRD (vendor uImage has built-in initrd)..."
  send "bootm 0x41000000 - 0x43000000"

  echo "[$(date '+%H:%M:%S')] Boot command sent. Waiting 90s for userspace..."
} >> $LOG 2>&1

sleep 90

{
  echo "[$(date '+%H:%M:%S')] Checking SSH reachability..."
  if ping -c1 -W2 192.168.0.151 2>/dev/null; then
    echo "[$(date '+%H:%M:%S')] SSH PING OK"
    sshpass -p orangepi ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 orangepi@192.168.0.151 "uptime" >> $LOG 2>&1 && echo "[$(date '+%H:%M:%S')] SSH OK" || echo "[$(date '+%H:%M:%S')] SSH FAILED"
  else
    echo "[$(date '+%H:%M:%S')] SSH UNREACHABLE"
  fi

  echo "[$(date '+%H:%M:%S')] Killing reader..."
  kill $(cat /tmp/ser_reader.pid 2>/dev/null) 2>/dev/null
  echo "[$(date '+%H:%M:%S')] DONE. Serial log: $LOG"
} >> $LOG 2>&1
