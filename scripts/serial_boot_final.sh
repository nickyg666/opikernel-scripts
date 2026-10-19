#!/bin/bash
# serial_boot_final.sh — proven cat pattern + boot commands + persistent logging
# KEY: uses (sudo setsid bash -c "exec cat ...") subshell — proven working

DEV=/dev/ttyACM0
LOG=/home/host/pvrgl-work/boot_final.log
PIDFILE=/tmp/ser_final.pid

echo "[$(date '+%H:%M:%S')] === VENDOR KERNEL BOOT ==="

# Kill stale cats
pkill -f "cat $DEV" 2>/dev/null
sleep 1

# Start serial capture with PROVEN subshell pattern
(sudo setsid bash -c "exec cat $DEV >> $LOG") </dev/null >/dev/null 2>&1 &
echo $! > $PIDFILE
sleep 1
echo "[$(date '+%H:%M:%S')] Reader started (PID=$(cat $PIDFILE))"

# Power cycle
echo "[$(date '+%H:%M:%S')] Power cycling..."
python3 /home/host/smartplug.py reboot >/dev/null 2>&1

# Wait for U-Boot + Enter spam
echo "[$(date '+%H:%M:%S')] Waiting for U-Boot, spamming Enter..."
sleep 8
for i in $(seq 1 40); do
  printf "\r" > $DEV 2>/dev/null
  sleep 0.25
done
echo "[$(date '+%H:%M:%S')] Spam done, waiting 5s..."
sleep 5

# Check what we captured
SIZE=$(wc -c < $LOG 2>/dev/null || echo 0)
echo "[$(date '+%H:%M:%S')] Log: $SIZE bytes"
grep -a "=> \|Hit any\|U-Boot" $LOG 2>/dev/null | tail -5

# Check for U-Boot prompt
if grep -q "=> " $LOG 2>/dev/null; then
  echo "[$(date '+%H:%M:%S')] U-Boot prompt found!"
else
  echo "[$(date '+%H:%M:%S')] No prompt yet — waiting more..."
  sleep 5
fi

# Boot commands — wait for prompt, then send
bootargs='root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm'

send() {
  echo "[$(date '+%H:%M:%S')] CMD: $1"
  printf "%s\r" "$1" > $DEV 2>/dev/null
  sleep 2
}

send "setenv bootargs $bootargs"
sleep 1
send "ext4load mmc 0:1 0x41000000 boot/uImage"
sleep 10
send "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb"
sleep 3
send "bootm 0x41000000 - 0x43000000"

echo "[$(date '+%H:%M:%S')] Kernel boot in progress, waiting 90s..."
sleep 90

echo "=== FINAL STATE ==="
SIZE_FINAL=$(wc -c < $LOG 2>/dev/null || echo 0)
echo "Log: $SIZE bytes -> $SIZE_FINAL bytes (+$((SIZE_FINAL - SIZE)))"
echo "=== Key markers ==="
grep -a "login:\|Starting kernel\|EXT4\|aic8800\|VFS:\|root@\|Kernel" $LOG 2>/dev/null | tail -10
echo "=== CHECKING SSH ==="
if sshpass -p orangepi ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 orangepi@192.168.0.151 "uptime" 2>/dev/null; then
  echo "BOARD ONLINE!"
else
  echo "Board still offline — check log"
fi
echo "=== DONE ==="
