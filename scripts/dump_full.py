#!/usr/bin/env python3
"""dump_full.py — Dump entire 465-fixed boot.scr content via md.b.
Usage: sudo python3 dump_full.py
"""
import serial, sys, time, os, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/dump_full.log"

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

def send_cmd(ser, cmd, wait=3.0):
    ser.write(cmd.encode() + b'\r')
    time.sleep(0.1)
    out = b''
    deadline = time.time() + wait
    while time.time() < deadline:
        if ser.in_waiting:
            out += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return out.decode('utf-8', errors='replace')

def wait_for(ser, patterns, timeout=30):
    start = time.time()
    buf = b''
    while time.time() - start < timeout:
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            buf += data
            decoded = data.decode('utf-8', errors='replace')
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

# Load 465-fixed
log("Loading 465-fixed into RAM...")
resp = send_cmd(ser, "ext4load mmc 0:1 0x43200000 /boot/boot.scr.465-fixed", 10)

# Dump 4096 bytes at a time using md.b
all_hex = b''
for offset in [0, 4096]:
    log(f"Dumping from 0x{0x43200000 + offset:08x}...")
    resp = send_cmd(ser, f"md.b 0x{0x43200000 + offset:08x} 4096", 10)
    log(f"  Got {len(resp)} bytes")
    # Parse the response - extract hex bytes from lines
    for line in resp.split('\r'):
        line = line.strip()
        if line and not line.startswith('md.b') and '=>' not in line and len(line) > 10:
            # Lines look like: "43200000: 56 19 05 27 ..."
            parts = line.split(':', 1)
            if len(parts) == 2 and len(parts[0].strip()) == 8:
                # It's a valid line
                hex_part = parts[1].rsplit('   ', 1)[0] if '   ' in parts[1] else parts[1].split(' ', 17)[0]
                hex_bytes = hex_part.split()
                for hb in hex_bytes:
                    try:
                        all_hex += bytes([int(hb, 16)])
                    except:
                        pass

log(f"Total dumped: {len(all_hex)} bytes")
# Write raw bytes to a file
with open('/home/host/pvrgl-work/465-fixed-dump.bin', 'wb') as f:
    f.write(all_hex)
# Extract ASCII part (after 0x40 header offset)
if len(all_hex) > 0x40:
    ascii_part = all_hex[0x40:]
    log(f"ASCII content (first 500):\n{ascii_part[:500].decode('utf-8', errors='replace')}")

logf.close(); ser.close()
log(f"Log: {LOG} ({os.path.getsize(LOG)} bytes)")
log(f"Binary: /home/host/pvrgl-work/465-fixed-dump.bin")
