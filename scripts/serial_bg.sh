#!/bin/bash
# serial_bg.sh — Start background serial capture before power cycle.
# Run this FIRST, then do power cycle separately.
DEV=/dev/ttyACM0
LOG="/home/host/pvrgl-work/uboot_full_recover.log"

# Kill existing
pkill -f "cat $DEV" 2>/dev/null
pkill -f "uboot_full" 2>/dev/null
sleep 1

# Start fresh capture
exec sudo tee "$LOG" < "$DEV" > /dev/null &
BG_PID=$!
sleep 0.5

# Verify it's running
if kill -0 $BG_PID 2>/dev/null; then
    echo "[BG] Started PID=$BG_PID logging $DEV -> $LOG"
    echo $BG_PID > /tmp/serial_bg.pid
else
    echo "[BG] FAILED to start"
fi
