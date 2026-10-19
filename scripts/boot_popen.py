#!/usr/bin/env python3
"""Boot script: serial read/write in one process, survives parent death via setsid wrapper."""
import os, sys, time, subprocess, serial

DEV = "/dev/serial/by-id/usb-Raspberry_Pi_Pico_5054316540DA319C-if00"
LOG = "/home/host/pvrgl-work/boot_popen.log"
OUT = "/home/host/pvrgl-work/boot_popen.out"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = "[%s] %s" % (ts, msg)
    print(line, flush=True)
    with open(OUT, 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

def send(ser, cmd, delay=2):
    ser.write((cmd + '\r').encode())
    ser.flush()
    time.sleep(delay)
    log(">> " + cmd[:80])

log("=== Boot Popen: vendor kernel ===")

# Kill competing readers
sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
time.sleep(1)

# Open serial port for entire session
log("Opening %s..." % DEV)
ser = serial.Serial(DEV, 115200, timeout=1.0)
log("Serial connected")

# Power cycle
log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")

# Wait for U-Boot
log("Waiting 13s...")
time.sleep(13)

# Spam BREAK
log("BREAK spam...")
for _ in range(20):
    ser.write(b'\r')
    ser.flush()
    time.sleep(0.25)
time.sleep(3)

# Drain buffer
ser.timeout = 0.1
while ser.read(4096):
    pass
ser.timeout = 1.0

# Wait for U-Boot prompt
log("Waiting for '=>'...")
with open(LOG, 'wb') as logf:
    found = False
    for _ in range(20):
        time.sleep(1)
        buf = ser.read(4096)
        if buf:
            logf.write(buf); logf.flush()
        text = logf.read().decode('latin-1', errors='replace')
        if '=>' in text:
            log("U-Boot prompt found!")
            found = True
            break
    if not found:
        log("No U-Boot prompt!")
        sys.exit(1)

# Boot sequence
log("Sending vendor boot...")
send(ser, "setenv distro_bootcmd ''")
time.sleep(1)
send(ser, "setenv bootcmd \"ext4load mmc 0:1 0x41000000 boot/uImage && ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb && bootm 0x41000000 - 0x43000000\"", delay=3)
send(ser, "run bootcmd", delay=5)

log("Monitoring kernel boot (120s)...")
with open(LOG, 'ab') as logf:
    online = False
    for i in range(12):
        time.sleep(10)
        buf = ser.read(4096)
        if buf:
            logf.write(buf); logf.flush()
        sz = os.path.getsize(LOG)
        log("  T+%ds: %d bytes" % ((i+1)*10, sz))
        r = subprocess.run(
            ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=3", "orangepi@192.168.0.151", "uptime"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0:
            log("BOARD ONLINE: " + r.stdout.strip())
            online = True
            break
    if not online:
        log("WARNING: Board may not be online yet")

ser.close()
log("Done.")
