#!/bin/bash
# Send raw commands to ttyACM0 without logging (reader logs everything separately)
TTY="/dev/ttyACM0"
CMD="$1"
shift

if [ -z "$CMD" ]; then
    echo "Usage: $0 \"command string\""
    exit 1
fi

printf "%s\r\n" "$CMD" | sudo dd of="$TTY" bs=1 2>/dev/null
echo "Sent: $CMD"
