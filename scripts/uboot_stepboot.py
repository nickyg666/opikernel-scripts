#!/usr/bin/env python3
"""uboot_stepboot.py — Step-by-step boot: individual commands, see each response.
Usage: sudo python3 uboot_stepboot.py
"""
import serial, sys, time, os, signal, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/uboot_stepboot.log"

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
    log(f"FAILED: No prompt. Buffer: {data[-300:]}")
    logf.close(); ser.close(); sys.exit(1)
log(f"Found '{pat}' — sending break...")
ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
time.sleep(0.3); ser.write(b'\r'); time.sleep(1.0)
drain(ser); time.sleep(2)
log("U-Boot shell ready.")

# STEP-BY-STEP BOOT
K = "/boot/mainline/Image"
I = "/boot/mainline/tiny-uInitrd"
D = "/boot/mainline/sun60i-a733-orangepi-zero3w.dtb"
A = "console=ttyS0,115200 root=/dev/mmcblk1p1 rootwait rootfstype=ext4 modprobe.blacklist=aic8800_bt,aic8800_sdio loglevel=7 clk_ignore_unused"

steps = [
    ("Load kernel", f"ext4load mmc 0:1 0x41000000 {K}", 15),
    ("Load initrd", f"ext4load mmc 0:1 0x46000000 {I}", 15),
    ("Load DTB", f"ext4load mmc 0:1 0x44000000 {D}", 15),
    ("fdt addr", "fdt addr 0x44000000", 3),
    ("fdt resize", "fdt resize 65536", 3),
    ("set bootargs", f"setenv bootargs {A}", 3),
    ("print bootargs", "printenv bootargs", 3),
    ("booti", "booti 0x41000000 0x46000000 0x44000000", 3),
]

for name, cmd, wait in steps:
    log(f"=== Step: {name} ===")
    resp = send_cmd(ser, cmd, wait)
    # Check for errors
    if any(e in resp for e in ['ERROR', 'FDT_ERR', 'FAILED', 'not found', 'failed']):
        log(f"  *** ERROR in step '{name}' ***")
    # Special: after booti, wait for kernel output
    if name == "booti":
        log("Kernel booting, watching...")
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
                logf.write(decoded); logf.flush()
                
                if any(k in decoded for k in ['Kernel panic', 'BUG:', 'ERROR:', 'FDT_ERR']):
                    log(f"  *** ISSUE DETECTED ***")
                if 'login:' in decoded:
                    userspace = True
                    log("  *** USERSAPCE REACHED ***")
            if time.time() - last_dot > 15:
                elapsed = int(time.time() - boot_start)
                log(f"  [{elapsed}s | u={userspace}]")
                last_dot = time.time()
            if userspace or time.time() - boot_start > 90:
                break
            time.sleep(0.05)
        
        if not userspace:
            log(f"  WARNING: No userspace in 90s")
            # Final drain
            deadline = time.time() + 3
            while time.time() < deadline and ser.in_waiting:
                data = ser.read(ser.in_waiting)
                boot_buf += data
                logf.write(data.decode('utf-8', errors='replace')); logf.flush()
    time.sleep(0.5)

logf.close(); ser.close()

# SSH CHECK
log("Checking SSH...")
time.sleep(5)
ssh_ok = subprocess.run(["ping","-c","3","-W","2","192.168.0.151"], capture_output=True).returncode == 0

log(f"\n{'='*60}")
log(f"SSH={ssh_ok}")
log(f"Log: {LOG} ({os.path.getsize(LOG)} bytes)")
log(f"{'='*60}")
