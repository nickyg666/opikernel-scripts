#!/bin/bash
# Serial boot recovery — clean FIFO reader + direct command sending
TTY="/dev/ttyACM0"
LOGDIR="/home/host/opikernel/pvrgl-work"
PIPE="$LOGDIR/serial_pipe"
LOG="$LOGDIR/sercap_go.log"

kill_cats() {
    sudo kill -9 $(pgrep -f 'tee.*sercap') $(pgrep -f 'cat.*serial_pipe') $(pgrep -f 'cat.*ttyACM0') 2>/dev/null
    sleep 1
}

# Cleanup first
kill_cats
rm -f "$PIPE" "$LOG"
mkfifo "$PIPE"

# Start background reader: ttyACM0 -> FIFO -> tee -> log
# tee runs first so FIFO is open for reading
sudo tee "$LOG" < "$PIPE" &
TEE_PID=$!
sleep 0.5

# cat reads ttyACM0 and writes to FIFO
sudo setsid bash -c "exec cat $TTY > $PIPE" < /dev/null &
CAT_PID=$!
sleep 0.5

echo "tee PID=$TEE_PID, cat PID=$CAT_PID"
ps aux | grep -E "tee.*sercap|cat.*ttyACM0" | grep -v grep

# Send a command to ttyACM0
send() {
    local cmd="$1"
    printf "%s\r\n" "$cmd" | sudo dd of="$TTY" bs=1 2>/dev/null
    echo "SENT: $cmd"
}

# Boot sequence
send "ext4load mmc 0:1 0x41000000 boot/uImage"
sleep 4
send "ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb"
sleep 3
send "setenv bootargs root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm console=ttyS0,115200"
sleep 1
send "bootm 0x41000000 - 0x43000000"

echo "Bootcmd sent. Monitoring for 90s..."
for i in $(seq 1 9); do
    sleep 10
    SZ=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
    echo "[$((i*10))s] log size=$SZ"
    if grep -q "login:" "$LOG" 2>/dev/null; then
        echo "LOGIN DETECTED!"
        break
    fi
done

echo "Done. Log size: $(stat -c%s "$LOG" 2>/dev/null)"
