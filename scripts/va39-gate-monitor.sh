#!/bin/bash
# monitor script for cron: deterministic status of the va39 boot gate (no timestamps in output!)
LOG=$(ls -t /home/host/opikernel/pvrgl-work/sercap_pipeline4b_*.log 2>/dev/null | head -1)
if [ -z "$LOG" ]; then echo "NO-LOG"; exit 0; fi
state() { grep -ac "$1" "$LOG" 2>/dev/null | head -1; }
DONE=$(grep -ac 'PIPELINE4B DONE' "$LOG")
PANIC=$(grep -ac 'Kernel panic' "$LOG")
SHELL_=$(grep -ac 'login:\|/ #' "$LOG")
LINUX=$(grep -ac 'Linux version' "$LOG")
BLK=$(grep -aoE 'blk [0-9]+/[0-9]+' "$LOG" | tail -1)
EXTW=$(grep -ac 'Image.va39' "$LOG")
if [ "$DONE" -gt 0 ]; then
  echo "GATE-DONE panic=$PANIC linux=$LINUX shell=$SHELL_  tail: $(strings "$LOG" | tail -5 | tr '\n' ' ')"
elif [ "$PANIC" -gt 0 ]; then echo "GATE-PANIC linux=$LINUX blk=$BLK"
elif [ "$LINUX" -gt 0 ]; then echo "GATE-LINUX-BOOTING linux=$LINUX shell=$SHELL_ blk=$BLK"
else echo "GATE-TRANSFER blk=$BLK ext4write-hits=$EXTW"; fi
