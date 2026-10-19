#!/usr/bin/env python3
"""uboot_minimal.py — Boot with minimal bootargs to see kernel console output.
Usage: sudo python3 uboot_minimal.py
"""
import serial, sys, time, os, signal, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/uboot_minimal.log"

logf = open(LOG, 'w', buffering=1)
def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    logf.write(line + "\n"); logf.flush()

def signal_handler(sig, frame):
    log("[INTERRUPTED]"); logf.close(); sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

def drain(ser):
    total = 0
    for _ in range(20):
        if ser.in_waiting:
            n = ser.in_waiting
            ser.read(n); total += n
            time.sleep(0.1)
        else:
            time.sleep(0.2)
    return total

def send_cmd(ser, cmd, wait=2.0):
    log(f">>> {cmd[:90]}")
    ser.write(cmd.encode() + b'\r')
    time.sleep(0.1)
    out = b''
    deadline = time.time() + wait
    while time.time() < deadline:
        if ser.in_waiting:
            out += ser.read(ser.in_waiting)
        time.sleep(0.05)
    resp = out.decode('utf-8', errors='replace')
    for line in resp.split('\r'):
        line = line.strip()
        if line and '=>' not in line:
            log(f"    {line}")
    return resp

def wait_for(ser, patterns, timeout=30):
    start = time.time()
    buf = b''
    while time.time() - start < timeout:
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            buf += data
            decoded = buf.decode('utf-8', errors='replace')
            for p in patterns:
                if p in decoded:
                    return p, decoded
        time.sleep(0.05)
    return None, buf.decode('utf-8', errors='replace')

# KILL & OPEN
log("Killing existing readers...")
subprocess.run("sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1", shell=True)
time.sleep(2)
log("Opening serial...")
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False; ser.rts = False
time.sleep(0.5)
drained = drain(ser)
log(f"Drained {drained} stale bytes")

# POWER CYCLE
log("Power cycle...")
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","off","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
time.sleep(5)
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","on","--model","WLPP1CFH","D03F271583AE"], capture_output=True)

# WAIT FOR U-BOOT
log("Waiting for U-Boot...")
pat, data = wait_for(ser, ['Hit any key', '=>'], timeout=30)
if not pat:
    log(f"FAILED: No prompt"); logf.close(); ser.close(); sys.exit(1)
log(f"Found '{pat}' — sending break...")
ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
time.sleep(0.3); ser.write(b'\r'); time.sleep(1.0)
drain(ser); time.sleep(2)
log("U-Boot shell ready.")

# LOAD ARTIFACTS
K = "/boot/mainline/Image"
I = "/boot/mainline/tiny-uInitrd"
D = "/boot/mainline/sun60i-a733-orangepi-zero3w.dtb"

log("Loading kernel...")
send_cmd(ser, f"ext4load mmc 0:1 0x41000000 {K}", 15)
log("Loading initrd...")
send_cmd(ser, f"ext4load mmc 0:1 0x46000000 {I}", 15)
log("Loading DTB...")
send_cmd(ser, f"ext4load mmc 0:1 0x44000000 {D}", 15)
log("fdt addr...")
send_cmd(ser, "fdt addr 0x44000000", 3)
log("fdt resize...")
send_cmd(ser, "fdt resize 65536", 3)

# MINIMAL BOOTARGS - just console + root + wait
MINIMAL_ARGS = "console=ttyS0,115200 root=/dev/mmcblk1p1 rootwait"
log(f"Setting minimal bootargs: {MINIMAL_ARGS}")
send_cmd(ser, f"setenv bootargs {MINIMAL_ARGS}", 3)

# BOOT
log("=== BOOTING ===")
send_cmd(ser, "booti 0x41000000 0x46000000 0x44000000", 3)

# WATCH with extended timeout
log("Watching kernel boot (120s max)...")
boot_start = time.time()
last_dot = boot_start
userspace = False
panic = False
boot_buf = b''

while time.time() - boot_start < 120:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        boot_buf += data
        decoded = data.decode('utf-8', errors='replace')
        logf.write(decoded); logf.flush()
        if any(k in decoded for k in ['Kernel panic', 'BUG:', 'ERROR:', 'Panic']):
            log("  *** PANIC/ERROR ***")
        if 'login:' in decoded:
            userspace = True; log("  *** USERSAPCE ***")
    
    if time.time() - last_dot > 20:
        elapsed = int(time.time() - boot_start)
        log(f"  [{elapsed}s | u={userspace}]")
        last_dot = time.time()
    
    if userspace:
        break
    time.sleep(0.05)

# Final drain
deadline = time.time() + 5
while time.time() < deadline and ser.in_waiting:
    data = ser.read(ser.in_waiting)
    boot_buf += data
    logf.write(data.decode('utf-8', errors='replace')); logf.flush()

logf.close(); ser.close()

# SSH CHECK
log("Checking SSH...")
time.sleep(5)
ssh_ok = subprocess.run(["ping","-c","3","-W","2","192.168.0.151"], capture_output=True).returncode == 0

log(f"\n{'='*60}")
log(f"RESULT: SSH={ssh_ok} userspace={userspace}")
log(f"Log: {LOG} ({os.path.getsize(LOG)} bytes)")
log(f"{'='*60}")

# Extract key lines from boot_buf
decoded_full = boot_buf.decode('utf-8', errors='replace')
for line in decoded_full.split('\n'):
    stripped = line.strip()
    if stripped and len(stripped) > 3:
        log(f"  K: {stripped}")
