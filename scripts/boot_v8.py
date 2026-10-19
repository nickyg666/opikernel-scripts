#!/usr/bin/env python3
"""Serial boot v8: intercept during autoboot countdown (<9s), fix bootcmd on SD.
Strategy:
1. Power on, start daemon reader
2. Wait 7s (during autoboot countdown)
3. Send BREAK/Enter spam during countdown window
4. Catch U-Boot prompt BEFORE bootcmd fires
5. Set bootcmd to vendor kernel + blacklist
6. Run bootcmd — correct kernel boots
"""
import os, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_v8.log"
PIDFILE = "/tmp/ser_v8.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Serial boot v8: intercept DURING autoboot ===")

# Kill existing cats
sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
time.sleep(1)

# Start forked daemon reader
log("Starting daemon reader...")
sh(f"rm -f {LOG}")
pid = os.fork()
if pid == 0:
    os.setsid()
    os.close(0); os.close(1); os.close(2)
    with open(LOG, 'wb') as out:
        with open(DEV, 'rb') as inp:
            while True:
                d = inp.read(4096)
                if d: out.write(d); out.flush()
                else: time.sleep(0.05)
    sys.exit(0)
else:
    with open(PIDFILE, 'w') as f:
        f.write(str(pid))
    time.sleep(2)
    log(f"Daemon PID={pid}, alive: {sh(f'ps -p {pid} -o pid 2>/dev/null && echo YES || echo NO').stdout.strip()}")

# Power cycle
log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")

# CRITICAL: intercept DURING the 9s autoboot countdown window
log("Waiting 7s then spamming Enter during countdown...")
time.sleep(7)

log("Sending Enter spam during countdown window...")
for _ in range(30):
    with open(DEV, 'wb') as f:
        f.write(b'\r')
    time.sleep(0.25)

time.sleep(3)
log("Countdown should be over — check for prompt...")

# Check if we caught U-Boot
with open(LOG, 'rb') as f:
    text = f.read().decode('latin-1', errors='replace')
if '=>' in text:
    log("SUCCESS: Caught U-Boot prompt!")
else:
    log("WARNING: No prompt yet, waiting more...")
    time.sleep(5)
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if '=>' not in text:
        log("WARNING: Still no prompt — may have missed window")

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)

# Read current bootcmd to see what's there
log("Reading current bootcmd...")
send("printenv bootcmd", delay=3)
with open(LOG, 'rb') as f:
    text = f.read().decode('latin-1', errors='replace')
import re
chunks = re.findall(r'[\x20-\x7e]{6,}', text)
for c in chunks:
    if 'bootcmd' in c.lower() or 'Image' in c or 'uImage' in c:
        log(f"  {c[:200]}")

# Set bootcmd to vendor kernel with correct bootargs
bootargs = (
    "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 "
    "earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 "
    "console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused "
    "swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm"
)

vendor_bootcmd = (
    "ext4load mmc 0:1 0x41000000 boot/uImage && "
    "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb && "
    "setenv bootargs {} && bootm 0x41000000 - 0x43000000"
).format(bootargs)

log("Setting NEW bootcmd (vendor kernel + aic8800 blacklist)...")
send(f"setenv bootcmd \"{vendor_bootcmd}\"", delay=3)

log("Setting bootdelay -1...")
send("setenv bootdelay -1", delay=2)

log("Saving env to SD (persistence)...")
send("saveenv", delay=5)

log("Running new bootcmd...")
send("boot", delay=5)

# Monitor boot
log("Monitoring for 120s...")
for i in range(12):
    time.sleep(10)
    sz = os.path.getsize(LOG)
    log(f"  T+{(i+1)*10}s: {sz} bytes")
    r = subprocess.run(
        ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
         "-o", "ConnectTimeout=3", "orangepi@192.168.0.151", "uptime"],
        capture_output=True, text=True, timeout=8
    )
    if r.returncode == 0:
        log(f"BOARD ONLINE: {r.stdout.strip()}")
        break

log("=== FINAL ===")
with open(LOG, 'rb') as f:
    data = f.read()
text = data.decode('latin-1', errors='replace')
chunks = re.findall(r'[\x20-\x7e]{6,}', text)
for m in ["login:", "Starting kernel", "EXT4", "aic8800", "root@", "Kernel panic", "VFS:", "CPU:"]:
    hits = [c for c in chunks if m in c]
    if hits:
        log(f"'{m}': {hits[-1][:150]}")
log("=== DONE ===")
