#!/bin/bash
# Serial FIFO capture: reader (tee) + writer (cat ttyACM0) in one persistent script
LOGDIR="/home/host/opikernel/pvrgl-work"
PIPE="$LOGDIR/serial_pipe"
LOG="$LOGDIR/sercap_go.log"

rm -f "$PIPE" "$LOG"
mkfifo "$PIPE"

# Reader: FIFO -> log (stdout of tee goes to log)
sudo tee "$LOG" < "$PIPE" &
# Writer: ttyACM0 -> FIFO (stdin=fifo, reads ttyACM0 via bash redirection)
sudo bash -c "cat > '$PIPE'" < /dev/null &

echo "FIFO setup done. Reader=$(pgrep -f 'tee.*sercap') Writer=$(pgrep -f 'cat.*serial_pipe')"
sleep 300
