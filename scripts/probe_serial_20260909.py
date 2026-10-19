#!/usr/bin/env python3
"""Probe /dev/ttyACM0: send CR, report what comes back (U-Boot alive?)."""
import serial, time, sys

port = "/dev/ttyACM0"
baud = int(sys.argv[1]) if len(sys.argv) > 1 else 1500000
s = serial.Serial(port, baud, timeout=0.2)
s.reset_input_buffer()
buf = b""
for _ in range(6):
    s.write(b"\r")
    time.sleep(0.35)
    if s.in_waiting:
        buf += s.read(s.in_waiting)
time.sleep(0.5)
if s.in_waiting:
    buf += s.read(s.in_waiting)
s.close()
txt = buf.decode("utf-8", "replace")
print("BAUD", baud, "BYTES", len(buf))
print(repr(txt[-600:]))
