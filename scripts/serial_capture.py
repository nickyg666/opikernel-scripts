#!/usr/bin/env python3
"""Serial capture for /dev/opiz3w-serial — survives pkill of 'cat' processes."""
import os, sys, time

LOG = sys.argv[1] if len(sys.argv) > 1 else '/home/host/opikernel/pvrgl-work/sercap.73'
PORT = '/dev/opiz3w-serial'
BAUD = 115200

# Configure serial port
import subprocess
subprocess.run(['stty', '-F', PORT, str(BAUD), 'raw', '-echo', '-echoe', '-echok'], check=False)

fd = os.open(PORT, os.O_RDONLY | os.O_NONBLOCK)
buf = bytearray()
with open(LOG, 'ab') as f:
    while True:
        try:
            data = os.read(fd, 4096)
        except OSError:
            time.sleep(0.05)
            continue
        if data:
            buf.extend(data)
            f.write(bytes(buf))
            f.flush()
            buf.clear()
        else:
            time.sleep(0.05)