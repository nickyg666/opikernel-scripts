#!/usr/bin/env python3
"""Daemon serial capture using Python's os.fork() — survives parent exit."""
import os, time, sys

DEV = "/dev/ttyACM1"
LOG = "/home/host/pvrgl-work/boot_daemon.log"
PIDFILE = "/home/host/opikernel/pvrgl-work/ser_daemon.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

log("Forking reader daemon...")
os.system(f"rm -f {LOG}")

pid = os.fork()
if pid == 0:
    # Child — become daemon
    os.setsid()
    os.close(0)  # close stdin
    os.close(1)  # close stdout
    os.close(2)  # close stderr
    with open(LOG, 'wb') as f:
        with open(DEV, 'rb') as ser:
            while True:
                data = ser.read(4096)
                if data:
                    f.write(data)
                    f.flush()
                else:
                    time.sleep(0.1)
    sys.exit(0)
else:
    # Parent
    with open(PIDFILE, 'w') as f:
        f.write(str(pid))
    log(f"Daemon PID={pid}")
    time.sleep(2)
    # Check if child is alive
    result = os.waitpid(pid, os.WNOHANG)
    if result[0] == 0:
        log("Daemon ALIVE")
    else:
        log(f"Daemon died immediately: {result}")

# Now continue with boot sequence
log("Power cycling...")
os.system("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(4)
os.system("python3 /home/host/smartplug.py on 2>/dev/null")
log("Waiting 12s...")
time.sleep(12)

# Check capture
sz = os.path.getsize(LOG)
log(f"Log size: {sz} bytes")

# Enter spam
log("Spamming Enter...")
for _ in range(30):
    with open(DEV, 'wb') as f:
        f.write(b'\r')
    time.sleep(0.25)
time.sleep(5)

# Read log
with open(LOG, 'rb') as f:
    data = f.read()
text = data.decode('latin-1', errors='replace')
if '=> ' in text or 'Hit any' in text:
    log("U-Boot prompt found!")
else:
    log("No prompt — sending commands anyway")
    log("Log excerpt:")
    import re
    chunks = re.findall(r'[\x20-\x7e]{6,}', text)
    for c in chunks[-10:]:
        log(f"  {c}")

# Boot commands
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

send(f"setenv bootargs {bootargs}", delay=2)
send("ext4load mmc 0:1 0x41000000 boot/uImage", delay=12)
send("ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb", delay=3)
send("bootm 0x41000000 - 0x43000000", delay=5)

log("Waiting 90s for kernel...")
time.sleep(30)
sz2 = os.path.getsize(LOG)
log(f"Log: {sz} -> {sz2} bytes (+{sz2-sz})")
time.sleep(60)

log("=== FINAL ===")
sz3 = os.path.getsize(LOG)
log(f"Log: {sz} -> {sz3} bytes (+{sz3-sz})")

# Check SSH
import subprocess
r = subprocess.run(
    ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
     "-o", "ConnectTimeout=5", "orangepi@192.168.0.151", "uptime"],
    capture_output=True, text=True, timeout=10
)
if r.returncode == 0:
    log(f"BOARD ONLINE: {r.stdout.strip()}")
else:
    log(f"Board offline")
    with open(LOG, 'rb') as f:
        data = f.read()
    text = data.decode('latin-1', errors='replace')
    for m in ["login:", "Starting kernel", "EXT4", "root@", "Kernel", "=>"]:
        if m in text:
            import re
            chunks = re.findall(r'[\x20-\x7e]{6,}', text)
            for c in chunks:
                if m in c:
                    log(f"  '{m}': {c[:100]}")

log("=== DONE ===")
