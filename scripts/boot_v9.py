#!/usr/bin/env python3
"""Serial boot v9: intercept right at countdown end, disable distro_bootcmd.
Timing: distro_bootcmd fires ~1-2s after countdown ends.
Strategy: wait for countdown message, immediately send Enter to get prompt,
before distro_bootcmd has time to fire.
"""
import os, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_v9.log"
PIDFILE = "/tmp/ser_v9.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Serial boot v9: distro_bootcmd kill ===")

# Kill cats
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
    log(f"Daemon PID={pid}")

# Power cycle
log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")

# Wait 8.5s (U-Boot starts at 0, countdown at ~9s)
log("Waiting 8.5s for U-Boot to start...")
time.sleep(8)

# Now poll for U-Boot to appear
log("Polling for U-Boot prompt (watching for countdown end + distro_bootcmd)...")
start = time.time()
prompt_found = False
while time.time() - start < 5:
    with open(LOG, 'rb') as f:
        data = f.read()
    text = data.decode('latin-1', errors='replace')
    if '=>' in text and 'Hit any key' not in text:
        log("U-Boot prompt found! (before distro_bootcmd fired)")
        prompt_found = True
        break
    # Also check for distro_bootcmd to know if we missed it
    if 'distro_bootcmd' in text or 'run distro_bootcmd' in text:
        log("WARNING: distro_bootcmd already fired!")
        break
    time.sleep(0.1)

if not prompt_found:
    log("Prompt not found, trying Enter spam...")
    for _ in range(20):
        with open(DEV, 'wb') as f:
            f.write(b'\r')
        time.sleep(0.2)
    time.sleep(2)
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if '=>' in text:
        prompt_found = True
        log("Got prompt via spam")
    else:
        log("STILL no prompt — checking state...")
        time.sleep(3)

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)

# Disable distro_bootcmd (the villain that auto-boots mainline kernel)
log("Killing distro_bootcmd...")
send("setenv distro_bootcmd", delay=2)
send("setenv distro_bootcmd \"\"", delay=2)

# Also kill any other auto-boot
send("setenv bootcmd", delay=2)  # Show what's there
send("setenv bootcmd \"\"", delay=2)  # Clear

# Set our bootcmd to vendor kernel
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

log("Setting bootcmd to vendor kernel...")
send(f"setenv bootcmd \"{vendor_bootcmd}\"", delay=3)

# Run boot
log("Running bootcmd...")
send("boot", delay=5)

# Monitor
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
import re
chunks = re.findall(r'[\x20-\x7e]{6,}', text)
for m in ["login:", "Starting kernel", "EXT4", "aic8800", "root@", "Kernel panic", "VFS:", "CPU:", "AW istr"]:
    hits = [c for c in chunks if m in c]
    if hits:
        log(f"'{m}': {hits[-1][:200]}")
log("=== DONE ===")
