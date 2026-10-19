#!/usr/bin/env python3
"""Persistent serial monitor using pyserial. Auto-creates timestamped log file."""
import datetime, serial, signal, sys, os, time

PORT = "/dev/ttyACM1"
LOG_DIR = "/home/host/opikernel/pvrgl-work"
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, f"sercap_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

def handler(sig, frame):
    ser.close()
    sys.exit(0)

ser = serial.Serial(PORT, 115200, timeout=1)
signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)

with open(LOG, "ab") as f:
    while True:
        data = ser.read(4096)
        if data:
            f.write(data)
            f.flush()
        time.sleep(0.01)
