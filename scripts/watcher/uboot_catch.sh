#!/bin/bash
# Tail ttyS0.log; when U-Boot autoboot countdown appears, send a key IMMEDIATELY (local, no ssh latency)
D=/dev/ttyS0
LOG=/home/orangepi/uart_capture/ttyS0.log
LAST_LINE=$(wc -l < $LOG)
echo "watching ttyS0.log from line $LAST_LINE for autoboot window..."
tail -n +$((LAST_LINE+1)) -F $LOG | while read -r l; do
  case "$l" in
    *"Hit any key to stop autoboot"*)
      printf " " > $D; printf " " > $D; printf " " > $D
      echo "CAUGHT autoboot at $(date +%T)"
      exit 0
      ;;
  esac
done
