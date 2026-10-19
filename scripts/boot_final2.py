#!/usr/bin/env python3
"""Serial boot FINAL: disable distro_bootcmd, set vendor bootcmd, run bootcmd (not boot).
Key insight from v8/v9 analysis:
- distro_bootcmd runs at end of countdown (~T+9s), loads mainline kernel
- Calling `boot` re-triggers distro_bootcmd if it's still set
- Solution: setenv distro_bootcmd "", setenv bootcmd <vendor>, run bootcmd (single-shot)
"""
import os, sys, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_final2.log"
PIDFILE = "/tmp/ser_final2.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Serial boot FINAL: distro_bootcmd disable ===")

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

# Wait for U-Boot to appear, then spam during countdown
log("Waiting 8s...")
time.sleep(8)

# Poll for countdown message (appears at ~T+9.5s)
log("Polling for countdown...")
start = time.time()
countdown_seen = False
while time.time() - start < 4:
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if 'Hit any key' in text or 'stop autoboot' in text:
        log("Countdown visible! Spamming Enter...")
        countdown_seen = True
        for _ in range(20):
            with open(DEV, 'wb') as f:
                f.write(b'\r')
            time.sleep(0.2)
        break
    time.sleep(0.1)

if not countdown_seen:
    log("Countdown not seen — direct Enter spam...")
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

if not prompt_found:
    log("WARNING: no U-Boot prompt")

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)

# KEY STEP: disable distro_bootcmd (the villain!)
log("Disabling distro_bootcmd...")
send("setenv distro_bootcmd \"\"", delay=2)

# Set our bootcmd to vendor kernel with blacklist
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

# CRITICAL: use 'run bootcmd' NOT 'boot' (boot would re-trigger distro_bootcmd)
log("Running vendor bootcmd (via 'run bootcmd')...")
send("run bootcmd", delay=5)

# Monitor boot
log("Monitoring for 120s...")
sz_start = os.path.getsize(LOG)
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
        break

log("=== FINAL ===")
log(f"Log grew: {sz_start} -> {sz} (+{sz-sz_start})")
with open(LOG, 'rb') as f:
    data = f.read()
text = data.decode('latin-1', errors='replace')
import re
chunks = re.findall(r'[\x20-\x7e]{6,}', text)
for m in ["login:", "Starting kernel", "EXT4", "aic8800", "root@", "Kernel panic", "VFS:", "CPU:", "AW istr", "distro_bootcmd"]:
    hits = [c for c in chunks if m in c]
    if hits:
        log(f"'{m}': {hits[-1][:200]}")
log("=== DONE ===")
