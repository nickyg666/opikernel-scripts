#!/usr/bin/env python3
"""Persistent pico serial capture for opiz3w board console.
Opens /dev/ttyACM0, keeps it open, logs all bytes with timestamps.
Usage: sudo python3 ser_capture.py <logfile>
Kill with SIGTERM/SIGINT. Reopens on error (port can be dropped by USB resets).
"""
import sys, time, os, signal, serial

PORT = "/dev/ttyACM0"
BAUD = 115200
LOGF = sys.argv[1] if len(sys.argv) > 1 else "/home/host/pvrgl-work/ser_capture.log"

running = True
def stop(sig, frame):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def log(line: bytes):
    ts = time.strftime("%H:%M:%S")
    with open(LOGF, "ab") as f:
        f.write(f"[{ts}] ".encode() + line + b"\n")

log(b"=== capture start ===")
while running:
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5, rtscts=False, dsrdtr=False)
        ser.setDTR(False)  # do NOT pulse DTR on open
        log(b"=== port opened ===")
        buf = b""
        while running:
            try:
                chunk = ser.read(4096)
            except serial.SerialException as e:
                log(f"=== read err {e} ===".encode())
                break
            if chunk:
                buf += chunk
                # flush lines
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    log(line)
            else:
                if buf:
                    log(buf)
                    buf = b""
        try:
            ser.close()
        except Exception:
            pass
    except Exception as e:
        log(f"=== open err {e} ===".encode())
        time.sleep(2)
log(b"=== capture end ===")
