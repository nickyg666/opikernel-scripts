#!/bin/bash
# Atomic vendor kernel boot: cat capture + power cycle + U-Boot intercept + boot
set -x
DEV=/dev/ttyACM0
LOG=/home/host/pvrgl-work/boot_atomic.log
PIDFILE=/tmp/ser_atomic.pid

rm -f "$LOG"

# Start persistent capture (proven subshell pattern)
(sudo setsid bash -c "exec cat $DEV >> $LOG") </dev/null >/dev/null 2>&1 &
echo $! > "$PIDFILE"
sleep 1

# Power cycle
python3 /home/host/smartplug.py off 2>/dev/null
sleep 3
python3 /home/host/smartplug.py on 2>/dev/null

# Enter spam during boot
sleep 8
for i in $(seq 1 60); do
  printf "\r" > "$DEV" 2>/dev/null
  sleep 0.25
done

# Now we should be at U-Boot prompt
sleep 3

# Read log and check for U-Boot
SIZE=$(wc -c < "$LOG" 2>/dev/null || echo 0)
echo "Log size: $SIZE bytes"

# Send boot commands
bootargs='root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm'

printf "setenv bootargs %s\r" "$bootargs" > "$DEV"
sleep 2
printf "ext4load mmc 0:1 0x41000000 boot/uImage\r" > "$DEV"
sleep 10
printf "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb\r" > "$DEV"
sleep 3
printf "bootm 0x41000000 - 0x43000000\r" > "$DEV"

# Wait for kernel
sleep 90

# Final check
SIZE_FINAL=$(wc -c < "$LOG" 2>/dev/null || echo 0)
echo "Final log: $SIZE bytes -> $SIZE_FINAL bytes (+$((SIZE_FINAL - SIZE)))"

# SSH check
if sshpass -p orangepi ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 orangepi@192.168.0.151 "uptime" 2>/dev/null; then
  echo "BOARD ONLINE"
else
  echo "Board offline, dumping log markers:"
  grep -a "login:\|Starting kernel\|EXT4\|aic8800\|root@\|Kernel" "$LOG" 2>/dev/null | tail -20
fi
