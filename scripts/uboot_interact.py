#!/usr/bin/env python3
"""Interact with U-Boot on /dev/ttyACM0 at 1500000 baud."""
import serial, sys, time

dev = "/dev/ttyACM0"
baud = 1500000
cmd = sys.argv[1] if len(sys.argv) > 1 else None

ser = serial.Serial(dev, baud, timeout=2)
ser.dtr = False
ser.rts = False
time.sleep(0.5)

# Drain any pending output
if ser.in_waiting:
    ser.read(ser.in_waiting)

if cmd:
    for ch in cmd:
        ser.write(ch.encode())
        time.sleep(0.01)
    ser.write(b"\n")
    time.sleep(0.1)

# Read response
out = b""
for _ in range(20):
    if ser.in_waiting:
        out += ser.read(ser.in_waiting)
    time.sleep(0.1)

ser.close()
sys.stdout.buffer.write(out)
sys.stdout.buffer.flush()
print(f"\n=== cmd: {cmd} ===", file=sys.stderr)
