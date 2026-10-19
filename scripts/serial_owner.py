#!/usr/bin/env python3
"""serial_owner.py — own the pico UART, send a command byte-paced, print reply.
Usage: sudo python3 serial_owner.py "<command>" [wait_seconds]
Prerequisite: no other process may hold /dev/ttyACM0."""
import serial, time, sys

DEV = "/dev/ttyACM0"
cmd = sys.argv[1]
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0

ser = serial.Serial(DEV, 115200, timeout=0.2)
time.sleep(0.3)
ser.reset_input_buffer()
for ch in cmd:
    ser.write(ch.encode())
    time.sleep(0.02)
ser.write(b"\n")

buf = b""
end = time.time() + wait
while time.time() < end:
    data = ser.read(256)
    if data:
        buf += data
        end = time.time() + wait  # keep reading while data flows
ser.close()
sys.stdout.buffer.write(buf[-4000:])
