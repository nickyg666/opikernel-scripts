#!/usr/bin/env python3
"""Serial boot p1-TIMED: poll for countdown message during window, intercept before distro_bootcmd fires.
Key: distro_bootcmd fires ~1s after countdown "Hit any key to stop autoboot: 0".
Must catch countdown message, not just U-Boot appearing."""
import os, time, subprocess

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/boot_p1_t.log"
PIDFILE = "/tmp/ser_p1t.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

log("=== Boot p1-TIMED: countdown intercept ===")

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

# Poll for U-Boot countdown message (appears at ~T+9s)
log("Waiting for U-Boot countdown message...")
start = time.time()
countdown_found = False
while time.time() - start < 15:
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if 'Hit any key' in text or 'stop autoboot' in text:
        elapsed = time.time() - start
        log(f"Countdown found at T+{elapsed:.1f}s! Spamming Enter...")
        countdown_found = True
        # Spam Enter aggressively during countdown
        for _ in range(40):
            with open(DEV, 'wb') as f:
                f.write(b'\r')
            time.sleep(0.15)
        break
    time.sleep(0.2)

if not countdown_found:
    log("Countdown not found in 15s — Enter spam anyway...")
    for _ in range(20):
        with open(DEV, 'wb') as f:
            f.write(b'\r')
        time.sleep(0.25)

# Wait for prompt
time.sleep(3)
prompt_found = False
for _ in range(15):
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    if '=>' in text and 'Hit any' not in text:
        prompt_found = True
        log("U-Boot prompt found!")
        break
    time.sleep(0.5)

def send(cmd, delay=2):
    with open(DEV, 'wb') as f:
        f.write((cmd + '\r').encode())
    time.sleep(delay)

# Disable distro_bootcmd (ensure it won't fire on Enter press)
log("Disabling distro_bootcmd...")
send("setenv distro_bootcmd \"\"", delay=2)

# Set our bootcmd (vendor kernel, no bootargs override)
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
log("Setting bootcmd...")
send(f"setenv bootcmd \"{vendor_bootcmd}\"", delay=3)

# Boot using run bootcmd (single-shot, no distro re-trigger)
log("Running bootcmd...")
send("run bootcmd", delay=5)

# Wait 25s for kernel to load + boot, then exit cleanly
log("Waiting 25s for kernel boot, then exiting...")
time.sleep(25)

sz = os.path.getsize(LOG)
log(f"Phase 1 complete. Log: {sz} bytes. EXITING cleanly.")
