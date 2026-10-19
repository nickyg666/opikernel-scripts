#!/bin/bash
# Test picocom serial capture
LOG=/tmp/picocom_test.log
HEX=/tmp/picocom_test.hex
DEV=/dev/ttyACM1
sudo rm -f $LOG $HEX

echo "Starting picocom for 5s..."
sudo picocom -b 115200 -g $HEX $DEV &
PICO_PID=$!
echo "Picocom PID: $PICO_PID"
sleep 5
kill $PICO_PID 2>/dev/null
sleep 1
echo "Log size: $(wc -c < $HEX 2>/dev/null || echo 0) bytes"
xxd $HEX | head -15
echo "---Strings---"
strings $HEX | head -20
