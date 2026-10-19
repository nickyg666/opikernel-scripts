#!/usr/bin/env python3
"""Persistent serial boot: uses start_new_session=True to fully detach cat."""
import subprocess, time, os, sys

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_persistent.log"
PIDFILE = "/tmp/ser_persistent.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Persistent serial boot ===")

# Start detached cat reader
log("Starting detached cat reader...")
sh(f"rm -f {LOG}")
pid = subprocess.Popen(
    ['cat', DEV],
    stdout=open(LOG, 'wb'),
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
    start_new_session=True
).pid
with open(PIDFILE, 'w') as f:
    f.write(str(pid))
log(f"Cat PID={pid}")

# Wait a bit
time.sleep(2)
log(f"Cat alive: {sh(f'ps -p {pid} -o pid,cmd 2>/dev/null && echo OK || echo DEAD').stdout.strip()}")
log(f"Log size: {os.path.getsize(LOG)} bytes")

# Power cycle
log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(4)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")
log("Waiting 12s for U-Boot...")
time.sleep(12)

# Check capture
sz1 = os.path.getsize(LOG)
log(f"Log after 12s: {sz1} bytes")
log(f"Cat still alive: {sh(f'ps -p {pid} -o pid,cmd 2>/dev/null && echo OK || echo DEAD').stdout.strip()}")

# Enter spam
log("Spamming Enter (30x)...")
for _ in range(30):
    with open(DEV, 'wb') as f:
        f.write(b'\r')
    time.sleep(0.25)
time.sleep(3)

# Check for U-Boot prompt
with open(LOG, 'rb') as f:
    data = f.read()
text = data.decode('latin-1', errors='replace')
if '=> ' in text:
    log("U-Boot prompt FOUND!")
else:
    log("No prompt — trying more waits...")
    time.sleep(5)

# Send boot commands
bootargs = (
    "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 "
    "earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 "
    "console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused "
    "swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm"
)

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)
    log(f"Sent: {cmd[:60]}")

log("Step 1: setenv bootargs...")
send(f"setenv bootargs {bootargs}", delay=2)

log("Step 2: load uImage...")
send("ext4load mmc 0:1 0x41000000 boot/uImage", delay=12)

log("Step 3: load DTB...")
send("ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb", delay=3)

log("Step 4: bootm...")
send("bootm 0x41000000 - 0x43000000", delay=5)

log("Kernel boot in progress, waiting 90s...")
time.sleep(30)
sz2 = os.path.getsize(LOG)
log(f"Log after 30s: {sz2} bytes (+{sz2-sz1})")
time.sleep(60)

log("=== FINAL ===")
log(f"Cat alive: {sh(f'ps -p {pid} -o pid,cmd 2>/dev/null && echo OK || echo DEAD').stdout.strip()}")
sz3 = os.path.getsize(LOG)
log(f"Log: {sz1} -> {sz3} bytes (+{sz3-sz1})")

# SSH check
r = subprocess.run(
    ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
     "-o", "ConnectTimeout=5", "orangepi@192.168.0.151", "uptime"],
    capture_output=True, text=True, timeout=10
)
if r.returncode == 0:
    log(f"BOARD ONLINE: {r.stdout.strip()}")
else:
    log(f"Board offline: {r.stderr.strip()}")
    log("=== Log markers ===")
    with open(LOG, 'rb') as f:
        data = f.read()
    text = data.decode('latin-1', errors='replace')
    for m in ["login:", "Starting kernel", "EXT4", "aic8800", "root@", "Kernel", "=>"]:
        if m in text:
            log(f"  '{m}' FOUND")

log("=== DONE ===")
