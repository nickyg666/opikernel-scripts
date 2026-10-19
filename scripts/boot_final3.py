#!/usr/bin/env python3
"""Serial boot FINAL v10: boot vendor kernel WITHOUT setting bootargs.
Root cause (from v8 analysis): vendor uImage has built-in initrd with bootargs
containing PARTUUID=486ea4ae-01. U-Boot's bootargs override is ignored because
the initrd (embedded in uImage) already set kernel cmdline.
Fix: don't setenv bootargs at all. Let vendor kernel use its defaults.
Then SSH into board and fix bootargs persistently from userspace.
"""
import os, sys, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_final3.log"
PIDFILE = "/tmp/ser_final3.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Boot FINAL v10: NO custom bootargs ===")

# Kill cats
sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
time.sleep(1)

# Fork daemon reader
log("Starting daemon reader...")
sh(f"rm -f {LOG}")
pid = os.fork()
if pid == 0:
    os.setsid()
    os.close(0); os.close(1); os.close(2)
    # Device FIRST so it gets FD 0 (stdin) — daemon reads from device.
    # Log file gets FD 1 (stdout) — daemon writes captured data.
    with open(DEV, 'rb') as inp:
        with open(LOG, 'wb') as out:
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

# Wait for U-Boot
log("Waiting 8s...")
time.sleep(8)

# Enter spam during countdown
log("Enter spam...")
for _ in range(20):
    with open(DEV, 'wb') as f:
        f.write(b'\r')
    time.sleep(0.25)

time.sleep(3)

# Get U-Boot prompt
prompt_found = False
for _ in range(10):
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if '=>' in text:
        prompt_found = True
        log("U-Boot prompt found!")
        break
    time.sleep(0.5)

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)

# Disable distro_bootcmd
log("Disabling distro_bootcmd...")
send("setenv distro_bootcmd \"\"", delay=2)

# Set minimal bootcmd (NO bootargs override!)
# Vendor kernel has built-in initrd with its own bootargs
vendor_bootcmd = (
    "ext4load mmc 0:1 0x41000000 boot/uImage && "
    "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb && "
    "bootm 0x41000000 - 0x43000000"
)
log("Setting vendor bootcmd (no bootargs override)...")
send(f"setenv bootcmd \"{vendor_bootcmd}\"", delay=3)

# Boot
log("Running vendor bootcmd...")
send("run bootcmd", delay=5)

# Monitor
log("Monitoring for 120s...")
sz_start = sz = os.path.getsize(LOG)
for i in range(12):
    time.sleep(10)
    sz = os.path.getsize(LOG)
    log(f"  T+{(i+1)*10}s: {sz} bytes (+{sz-sz_start})")
    r = subprocess.run(
        ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
         "-o", "ConnectTimeout=3", "orangepi@192.168.0.151", "uptime"],
        capture_output=True, text=True, timeout=8
    )
    if r.returncode == 0:
        log(f"BOARD ONLINE: {r.stdout.strip()}")
        # Once online, add the aic8800 blacklist and restart
        log("Board online! Adding aic8800 blacklist...")
        r2 = subprocess.run(
            ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=5", "orangepi@192.168.0.151",
             "echo 'options aic8800-sdio blacklist' | sudo tee /etc/modprobe.d/aic8800-btlpm.conf && echo blacklist > /tmp/blacklist.txt && sudo reboot"],
            capture_output=True, text=True, timeout=10
        )
        log(f"Blacklist added, reboot triggered: {r2.stdout.strip()}")
        break

log("=== FINAL ===")
log(f"Log grew: {sz_start} -> {sz} (+{sz-sz_start})")
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
