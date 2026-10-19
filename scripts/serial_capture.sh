#!/bin/bash
# Serial capture with FIFO — reader and writer separate so commands don't pollute log
LOGDIR="/home/host/opikernel/pvrgl-work"
PIPE="$LOGDIR/serial_pipe"
LOG="$LOGDIR/sercap_go.log"

rm -f "$PIPE" "$LOG"
mkfifo "$PIPE"

# Reader: FIFO -> log file (stays open)
sudo tee "$LOG" < "$PIPE" > /dev/null &

# Writer: ttyACM0 -> FIFO (with stdin detached)
sudo setsid bash -c "cat > '$PIPE'" < /dev/null &

echo "Reader PID: $(pgrep -f 'tee.*sercap_go.log')"
echo "Writer PID: $(pgrep -f 'cat.*serial_pipe')"
echo "FIFO ready at $PIPE"
