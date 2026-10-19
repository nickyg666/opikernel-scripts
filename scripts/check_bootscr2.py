#!/usr/bin/env python3
"""check_bootscr2.py — Check with raw serial output dump.
Usage: sudo python3 check_bootscr2.py
"""
import serial, sys, time, os, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/check_bootscr2.log"

logf = open(LOG, 'wb', buffering=0)
def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}\n"
    sys.stdout.write(line); sys.stdout.flush()
    logf.write(line.encode('utf-8')); logf.flush()

def drain(ser):
    for _ in range(20):
        if ser.in_waiting:
            ser.read(ser.in_waiting)
        time.sleep(0.1)

def wait_for(ser, patterns, timeout=30):
    start = time.time()
    buf = b''
    while time.time() - start < timeout:
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            buf += data
            decoded = buf.decode('utf-8', errors='replace')
            for p in patterns:
                if p in decoded:
                    return p, decoded
        time.sleep(0.05)
    return None, buf.decode('utf-8', errors='replace')

log("Killing readers...")
subprocess.run("sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1", shell=True)
time.sleep(2)

log("Opening serial...")
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False; ser.rts = False
time.sleep(0.5)
drain(ser)

log("Power cycle...")
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","off","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
time.sleep(5)
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","on","--model","WLPP1CFH","D03F271583AE"], capture_output=True)

log("Waiting for U-Boot...")
pat, _ = wait_for(ser, ['Hit any key', '=>'], timeout=30)
if not pat:
    log("FAILED: No prompt"); logf.close(); ser.close(); sys.exit(1)
log(f"Found '{pat}' — break...")
ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
time.sleep(0.3); ser.write(b'\r'); time.sleep(1.0)
drain(ser); time.sleep(2)

# Single ext4size test with full response capture
log("Testing ext4size with full response...")
ser.write(b'ext4size mmc 0:1 /boot/boot.scr\r')
time.sleep(3)
buf = b''
while ser.in_waiting:
    buf += ser.read(ser.in_waiting)
    time.sleep(0.1)

decoded = buf.decode('utf-8', errors='replace')
log(f"Full response: {repr(decoded)}")
log(f"Response hex: {buf.hex()}")

# Also test ls
log("\nTesting 'ls mmc 0:1 /boot':")
ser.write(b'ls mmc 0:1 /boot\r')
time.sleep(3)
buf = b''
while ser.in_waiting:
    buf += ser.read(ser.in_waiting)
    time.sleep(0.1)
log(f"ls response: {buf.decode('utf-8', errors='replace')}")

logf.close(); ser.close()
