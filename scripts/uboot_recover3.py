#!/usr/bin/env python3
"""uboot_recover3.py — Single-serial recovery: one process, one port, clean logs.
Everything goes to BOTH stdout and LOG file.
Run: sudo python3 uboot_recover3.py
"""
import serial, sys, time, os, signal, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/uboot_recover3.log"
FIXED_BOOTSCR = "/home/host/opikernel/stage/boot.scr.nofix"

logf = None
def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if logf:
        logf.write(line + "\n"); logf.flush()

def signal_handler(sig, frame):
    log("[INTERRUPTED]")
    if logf: logf.close()
    sys.exit(0)
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

def wait_for_pattern(ser, patterns, timeout=30):
    """Wait for any of the patterns; returns matched pattern + all data."""
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

# === SETUP ===
logf = open(LOG, 'w', buffering=1)

log("Step 1: Killing existing readers...")
subprocess.run("sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1", shell=True)
time.sleep(2)

log("Step 2: Opening serial...")
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False; ser.rts = False
time.sleep(0.5)
drained = drain(ser)
log(f"  Drained {drained} stale bytes")

log("Step 3: Power cycling...")
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","off","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
time.sleep(5)
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","on","--model","WLPP1CFH","D03F271583AE"], capture_output=True)

log("Step 4: Waiting for U-Boot 'Hit any key'...")
pat, data = wait_for_pattern(ser, ['Hit any key', 'stop auto', '=>'], timeout=30)
if not pat:
    log("FAILED: No U-Boot prompt")
    log(f"  Buffer: {data[-500:]}")
    logf.close(); ser.close()
    sys.exit(1)

log(f"  Found '{pat}' at {time.time():.1f}s — sending break...")
ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
time.sleep(0.3)
ser.write(b'\r'); time.sleep(1.0)
drain(ser)
time.sleep(2)

log("Step 5: U-Boot shell ready.")

# === INSPECT SD ===
log("=== SD Inspection ===")
for cmd in ["mmcinfo", "ext4size mmc 0:1 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb",
            "ext4size mmc 0:1 /boot/boot.scr"]:
    send_cmd(ser, cmd, 3.0)
    time.sleep(0.3)

# === SET DIRECT BOOTCMD (bypass boot.scr overlay failures) ===
log("=== Setting direct bootcmd (no overlay) ===")
bootcmd = (
    "setenv bootcmd '"
    "ext4load mmc 0:1 0x41000000 /boot/mainline/Image; "
    "ext4load mmc 0:1 0x46000000 /boot/mainline/tiny-uInitrd; "
    "ext4load mmc 0:1 0x44000000 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb; "
    "setenv bootargs console=ttyS0,115200 root=/dev/mmcblk1p1 rootwait rootfstype=ext4 "
    "earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 "
    "modprobe.blacklist=aic8800_bt,aic8800_sdio loglevel=7 clk_ignore_unused; "
    "booti 0x41000000 0x46000000 0x44000000'"
)
send_cmd(ser, bootcmd, 3.0)
send_cmd(ser, "saveenv", 5.0)
send_cmd(ser, "printenv bootcmd", 2.0)

# === BOOT ===
log("=== BOOTING KERNEL ===")
ser.write(b'boot\r')
time.sleep(2)
drain(ser)

# === WATCH KERNEL BOOT ===
log("Watching kernel boot (90s max)...")
boot_start = time.time()
last_dot = boot_start
userspace = False
panic = False
boot_buf = b''

while time.time() - boot_start < 90:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        boot_buf += data
        decoded = data.decode('utf-8', errors='replace')
        # Write to log file
        logf.write(decoded); logf.flush()
        # Print key events to console
        if 'Kernel panic' in decoded or 'BUG:' in decoded:
            panic = True
            log("  [PANIC DETECTED]")
        if 'login:' in decoded:
            userspace = True
            log("  [USERSAPCE REACHED]!!!")
    
    if time.time() - last_dot > 15:
        elapsed = int(time.time() - boot_start)
        log(f"  [{elapsed}s | u={userspace} p={panic}]")
        last_dot = time.time()
    
    if userspace or panic:
        break
    time.sleep(0.05)

# Final drain
deadline = time.time() + 3
while time.time() < deadline and ser.in_waiting:
    data = ser.read(ser.in_waiting)
    boot_buf += data
    decoded_last = data.decode('utf-8', errors='replace')
    logf.write(decoded_last); logf.flush()

logf.close(); ser.close()

# === SSH CHECK ===
log("Checking SSH...")
time.sleep(5)
ssh_ok = subprocess.run(["ping","-c","3","-W","2","192.168.0.151"], capture_output=True).returncode == 0

log(f"\n{'='*60}")
log(f"RESULT: SSH={ssh_ok} userspace={userspace} panic={panic}")
log(f"Full log: {LOG} ({os.path.getsize(LOG)} bytes)")
log(f"{'='*60}")

# Print key boot info from log
log("\n=== BOOT LOG EXCERPT ===")
decoded_full = boot_buf.decode('utf-8', errors='replace')
for line in decoded_full.split('\n'):
    if any(k in line for k in ['Kernel panic', 'login:', 'aic8800', 'BUG:', 'Linux version', 'Booting', 'EXT4-fs', 'VFS:', 'Freeing']):
        log(f"  {line.strip()}")
