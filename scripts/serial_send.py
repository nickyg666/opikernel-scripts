#!/usr/bin/env python3
"""serial_send.py — send a command to the pico UART byte-by-byte (no truncation).
Usage: sudo python3 serial_send.py "<command>"
"""
import serial, sys, time

dev = "/dev/ttyACM0"
cmd = sys.argv[1]

ser = serial.Serial(dev, 115200, timeout=1)
for ch in cmd:
    ser.write(ch.encode())
    time.sleep(0.02)
ser.write(b"\n")
ser.close()
print(f"sent {len(cmd)} chars")
