#!/bin/bash
# Serial boot v2: setsid reader survives shell exit
DEV=/dev/ttyACM0
LOG=${1:-/home/host/pvrgl-work/sercap_recovery.log}
PIDFILE=/tmp/ser_reader.pid

echo "[$(date '+%H:%M:%S')] Starting serial capture to $LOG"
sudo rm -f "$LOG"

# Kill any existing reader
sudo pkill -f "cat $DEV" 2>/dev/null
sleep 1

# Start persistent reader (setsid = survives parent death)
sudo setsid bash -c "exec cat $DEV >> $LOG" </dev/null >/dev/null 2>&1
READER_PID=$!
echo $READER_PID > $PIDFILE
echo "[$(date '+%H:%M:%S')] Reader PID: $READER_PID"
sleep 2

# Verify
if ps -p $READER_PID > /dev/null 2>&1; then
    echo "[$(date '+%H:%M:%S')] Reader ALIVE - $(ls -lh $LOG | awk '{print $5}')"
else
    echo "[$(date '+%H:%M:%S')] Reader FAILED to start"
    exit 1
fi

echo "[$(date '+%H:%M:%S')] Power cycling..."
python3 /home/host/smartplug.py off 2>/dev/null
sleep 5
python3 /home/host/smartplug.py on 2>/dev/null
echo "[$(date '+%H:%M:%S')] Power on. Waiting 12s for U-Boot..."
sleep 12

echo "[$(date '+%H:%M:%S')] Checking for U-Boot prompt..."
# Quick check of raw log
echo "--- Log size after U-Boot window ---"
ls -lh "$LOG"
echo "--- Last 20 bytes (hex) ---"
xxd "$LOG" | tail -5

# Send break/interrupt
printf "\r" > $DEV
sleep 0.5
printf "\r" > $DEV
sleep 3

# Read what's happened so far
echo "--- Boot messages captured ---"
strings "$LOG" | grep -E "Hit any|Autoboot|=>|U-Boot" | tail -5

# Send commands one by one
bootargs='root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm'

send() {
    printf "%s\r" "$1" > $DEV
    sleep 1.5
}

echo "[$(date '+%H:%M:%S')] Setting bootargs..."
send "setenv bootargs $bootargs"
sleep 1

echo "[$(date '+%H:%M:%S')] Loading uImage..."
send "load mmc 0:1 0x41000000 boot/uImage"
sleep 4

echo "[$(date '+%H:%M:%S')] Loading DTB..."
send "load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb"
sleep 2

echo "[$(date '+%H:%M:%S')] Booting (NO initrd)..."
send "bootm 0x41000000 - 0x43000000"

echo "[$(date '+%H:%M:%S')] Boot command sent. Waiting 90s..."
echo "--- Log size now ---"
ls -lh "$LOG"
sleep 90

echo "=== FINAL LOG STATE ==="
ls -lh "$LOG"
echo "--- Strings check ---"
strings "$LOG" | grep -E "login:|Starting kernel|Hit any|=>|EXT4|U-Boot|PVR|PowerVR|aic8800|root@|orangepi" | tail -15
echo "=== DONE ==="
