#!/usr/bin/env python3
"""Serial boot v6: cat background, Python send-only + polling reader."""
import sys, time, os, subprocess

DEV = "/dev/ttyACM1"
LOG = "/home/host/pvrgl-work/sercap_v6.log"
BAUD = 115200

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd, timeout=30):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout, r.stderr, r.returncode

def kill_cats():
    log("Killing existing serial readers...")
    sh("sudo pkill -f 'cat.*ttyACM' 2>/dev/null")
    time.sleep(1)

def start_cat():
    """Start cat in background, survive script exit via setsid."""
    sh(f"sudo rm -f {LOG}")
    # Use setsid to create new session — cat survives parent death
    cmd = f"sudo setsid bash -c 'exec cat {DEV} >> {LOG}' </dev/null >/dev/null 2>&1"
    r = subprocess.run(cmd, shell=True)
    time.sleep(2)
    # Verify cat is alive and log growing
    size1 = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    time.sleep(1)
    size2 = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    log(f"Cat started: log {size1}B -> {size2}B")
    return size2 > 0

def send(dev, cmd, delay=1.5):
    """Send command, drain echo, wait for response."""
    with open(dev, 'wb') as f:
        f.write(f"{cmd}\r".encode())
    time.sleep(delay)
    return read_log_tail(200)

def read_log_tail(n=500):
    """Read last n bytes of log as string."""
    if not os.path.exists(LOG):
        return ""
    with open(LOG, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        if size > n:
            f.seek(-n, 2)
        return f.read().decode('latin-1', errors='replace')

def grep_log(pat):
    """Return lines containing pat."""
    if not os.path.exists(LOG):
        return []
    with open(LOG, 'rb') as f:
        text = f.read().decode('latin-1', errors='replace')
    return [l.strip() for l in text.split('\r') if pat in l]

def size_log():
    return os.path.getsize(LOG) if os.path.exists(LOG) else 0

def wait_for(pat, timeout=60):
    """Poll log for pattern, return True if found."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if grep_log(pat):
            return True
        time.sleep(2)
        sys.stdout.write('.')
        sys.stdout.flush()
    return False

def show_tail():
    """Show readable ASCII tail of log."""
    with open(LOG, 'rb') as f:
        data = f.read()
    import re
    chunks = re.findall(r'[\x20-\x7e]{5,}', data.decode('latin-1', errors='replace'))
    # Show last 30 chunks
    for c in chunks[-30:]:
        print(f"  {c[:120]}", flush=True)

# ---- MAIN ----
log("=== Serial boot v6 ===")
kill_cats()

if not os.path.exists(DEV):
    log(f"ERROR: {DEV} not found")
    sys.exit(1)

log(f"Device: {DEV}, Log: {LOG}")

# Start cat background reader
ok = start_cat()
if not ok:
    log("WARNING: cat reader may not be capturing")

# Power cycle
log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")

# Wait for picoprobe to re-enumerate (board USB)
log("Waiting 15s for U-Boot + picoprobe...")
for i in range(15):
    time.sleep(1)
    sz = size_log()
    if sz > 100:
        log(f"Log has {sz} bytes at T+{i+1}s")
        break
    sys.stdout.write('.')
    sys.stdout.flush()

size_at_boot = size_log()
log(f"Log size: {size_at_boot} bytes")

# Show early boot
show_tail()

# Intercept autoboot — send breaks
log("Intercepting autoboot...")
for i in range(5):
    send(DEV, "", delay=0.3)
    if grep_log("=> ") or grep_log("Hit any key"):
        log(f"Prompt detected on try {i+1}")
        break
    time.sleep(0.5)

time.sleep(1)
show_tail()

# Wait for U-Boot prompt
log("Waiting for U-Boot prompt...")
prompt_found = False
for _ in range(20):
    time.sleep(1)
    if grep_log("=> "):
        log("U-Boot prompt FOUND")
        prompt_found = True
        break
    show_tail()

if not prompt_found:
    log("WARNING: no U-Boot prompt — proceeding anyway")
    time.sleep(3)

# Boot commands — send with delays
bootargs = (
    "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 "
    "earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 "
    "console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused "
    "swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm"
)

log("Step 1: setenv bootargs...")
resp = send(DEV, f"setenv bootargs {bootargs}", delay=3)
log(f"bootargs resp: {repr(resp[-150:])}")
time.sleep(1)

log("Step 2: load uImage (vendor kernel)...")
resp = send(DEV, "ext4load mmc 0:1 0x41000000 boot/uImage", delay=10)
log(f"uImage resp: {repr(resp[-200:])}")
time.sleep(1)

log("Step 3: load DTB...")
resp = send(DEV, "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb", delay=3)
log(f"DTB resp: {repr(resp[-200:])}")
time.sleep(1)

log("Step 4: bootm (NO initrd — vendor uImage has built-in)...")
resp = send(DEV, "bootm 0x41000000 - 0x43000000", delay=5)
log(f"bootm resp: {repr(resp[-300:])}")

log("Waiting 90s for kernel boot...")
time.sleep(30)
show_tail()
time.sleep(30)
show_tail()
time.sleep(30)

log("=== FINAL STATE ===")
final_size = size_log()
log(f"Log grew: {size_at_boot} -> {final_size} (+{final_size - size_at_boot})")

# Check SSH reachability
log("Checking SSH...")
r = subprocess.run(
    ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
     "-o", "ConnectTimeout=5", "orangepi@192.168.0.151", "uptime"],
    capture_output=True, text=True, timeout=10
)
if r.returncode == 0:
    log(f"BOARD ONLINE: {r.stdout.strip()}")
else:
    log(f"Board not reachable: {r.stderr.strip()}")

log("=== Key markers ===")
for pat in ["login:", "Starting kernel", "EXT4-fs: mounted", "aic8800", "VFS:", "Kernel panic", "root@"]:
    lines = grep_log(pat)
    if lines:
        for l in lines[-3:]:
            log(f"  {pat}: {l[:120]}")

log("=== DONE ===")
