#!/bin/bash
# Serial boot v3: proper background reader (stdin=/dev/null to detach from TTY)
DEV=/dev/ttyACM0
LOG=${1:-/home/host/pvrgl-work/sercap_recovery.log}
PIDFILE=/tmp/ser_reader.pid

echo "[$(date '+%H:%M:%S')] Serial boot v3"

# Kill existing readers
sudo pkill -f "cat $DEV" 2>/dev/null
sleep 1

# Start reader: stdin=/dev/null detaches from controlling TTY (no ioctl conflicts)
sudo bash -c "exec cat $DEV >> $LOG" </dev/null >/dev/null 2>&1 &
READER_PID=$!
echo $READER_PID > $PIDFILE
echo "[$(date '+%H:%M:%S')] Reader PID=$READER_PID"
sleep 2

# Verify alive + log growing
ps -p $READER_PID > /dev/null 2>&1 && echo "Reader alive" || { echo "READER DEAD"; exit 1; }
SIZE1=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
sleep 1
SIZE2=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
echo "Log: ${SIZE1}B -> ${SIZE2}B after 1s"

echo "[$(date '+%H:%M:%S')] Power cycle..."
python3 /home/host/smartplug.py off 2>/dev/null
sleep 5
python3 /home/host/smartplug.py on 2>/dev/null
echo "[$(date '+%H:%M:%S')] Waiting 12s for U-Boot..."
sleep 12

echo "=== Log at U-Boot window ==="
ls -lh "$LOG"
SIZE_UBOOT=$(stat -c%s "$LOG")

# Interrupting autoboot
printf "\r" > $DEV
sleep 0.5
printf "\r" > $DEV
sleep 3

# Check U-Boot prompt appeared
echo "--- U-Boot messages ---"
strings "$LOG" | grep -E "Hit any|Autoboot|=>|U-Boot" | tail -5

# Boot sequence
bootargs='root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm'

send() { printf "%s\r" "$1" > $DEV; sleep 1.5; }

send "setenv bootargs $bootargs"; sleep 1
echo "[$(date '+%H:%M:%S')] Loading uImage..."
send "load mmc 0:1 0x41000000 boot/uImage"; sleep 5
echo "[$(date '+%H:%M:%S')] Loading DTB..."
send "load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb"; sleep 2
echo "[$(date '+%H:%M:%S')] Booting..."
send "bootm 0x41000000 - 0x43000000"

echo "[$(date '+%H:%M:%S')] Waiting 90s for kernel..."
sleep 90

echo "=== Final state ==="
ls -lh "$LOG"
FINAL_SIZE=$(stat -c%s "$LOG")
echo "Log grew $((FINAL_SIZE - SIZE_UBOOT)) bytes during kernel boot"
strings "$LOG" | grep -E "login:|Starting kernel|Hit any|=>|EXT4|U-Boot|PVR|PowerVR|aic8800|root@|orangepi|Kernel uh->|CPU:" | tail -20
