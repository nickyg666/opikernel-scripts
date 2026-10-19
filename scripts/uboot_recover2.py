#!/usr/bin/env python3
"""uboot_recover2.py — Clean recovery with dual serial: foreground for commands, background for log.
Logs everything to file; stdout only shows script progress.
Run: sudo python3 uboot_recover2.py
"""
import serial, sys, time, os, signal, subprocess, threading

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/uboot_recover2.log"
FIXED_BOOTSCR = "/home/host/opikernel/stage/boot.scr.nofix"

# Global flag for bg thread
running = True

def bg_logger():
    """Background thread: log everything from serial to file."""
    try:
        ser = serial.Serial(DEV, BAUD, timeout=1)
        ser.dtr = False; ser.rts = False
        with open(LOG, 'wb') as f:
            while running:
                if ser.in_waiting:
                    data = ser.read(ser.in_waiting)
                    f.write(data); f.flush()
                time.sleep(0.05)
        ser.close()
    except Exception as e:
        print(f"[BG LOGGER ERROR: {e}]")

def signal_handler(sig, frame):
    global running
    running = False
    print("\n[interrupted]")
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
    sys.stdout.write(f"  >>> {cmd[:90]}\n")
    sys.stdout.flush()
    ser.write(cmd.encode() + b'\r')
    time.sleep(0.1)
    out = b''
    deadline = time.time() + wait
    while time.time() < deadline:
        if ser.in_waiting:
            out += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return out.decode('utf-8', errors='replace')

def print_lines(resp):
    for line in resp.split('\r'):
        line = line.strip()
        if line and '=>' not in line:
            sys.stdout.write(f"    {line}\n")
    sys.stdout.flush()

# === KILL EXISTING ===
sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] Killing existing serial readers...\n"); sys.stdout.flush()
subprocess.run("sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1", shell=True)
time.sleep(2)

# === START BACKGROUND LOGGER ===
sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] Starting background logger...\n"); sys.stdout.flush()
log_thread = threading.Thread(target=bg_logger, daemon=True)
log_thread.start()
time.sleep(1)

# === OPEN FOREGROUND SERIAL ===
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False; ser.rts = False
time.sleep(0.5)
drained = drain(ser)
sys.stdout.write(f"  Drained {drained} bytes, serial ready\n"); sys.stdout.flush()

# === POWER CYCLE ===
sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] Power cycling...\n"); sys.stdout.flush()
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","off","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
time.sleep(5)
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","on","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] Power on, waiting for U-Boot...\n"); sys.stdout.flush()

# === WAIT FOR U-BOOT ===
start = time.time()
prompt_found = False
while time.time() - start < 30:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        decoded = data.decode('utf-8', errors='replace')
        sys.stdout.write(decoded); sys.stdout.flush()
        if 'Hit any key' in decoded or 'stop auto' in decoded.lower():
            sys.stdout.write(f"\n[PROMPT at +{time.time()-start:.1f}s]\n"); sys.stdout.flush()
            ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
            time.sleep(0.3); ser.write(b'\r'); time.sleep(1.0)
            drain(ser)
            prompt_found = True
            break
        elif '=>' in decoded:
            prompt_found = True
            break
    time.sleep(0.05)

if not prompt_found:
    sys.stdout.write(f"[FAILED] No U-Boot prompt\n"); sys.stdout.flush()
    running = False; ser.close()
    sys.exit(1)

time.sleep(2); drain(ser)
sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] U-Boot shell acquired.\n\n"); sys.stdout.flush()

# === INSPECT SD ===
sys.stdout.write("=== SD Inspection ===\n"); sys.stdout.flush()
for cmd in ["mmcinfo", "ext4size mmc 0:1 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb",
            "ext4size mmc 0:1 /boot/boot.scr", "ext4size mmc 0:1 /stage/boot.scr.nofix"]:
    resp = send_cmd(ser, cmd, 3.0)
    print_lines(resp)
    time.sleep(0.3)

# === WRITE FIXED BOOTSCR ===
sys.stdout.write("\n=== Deploying fixed boot.scr ===\n"); sys.stdout.flush()
if os.path.exists(FIXED_BOOTSCR):
    size = os.path.getsize(FIXED_BOOTSCR)
    sys.stdout.write(f"  Host file: {FIXED_BOOTSCR} ({size} bytes)\n"); sys.stdout.flush()
    
    # Create /stage directory
    sys.stdout.write("  Creating /stage directory...\n"); sys.stdout.flush()
    resp = send_cmd(ser, "ext4mkdir mmc 0:1 /stage", 3.0)
    print_lines(resp)
    
    # Load host file into RAM at 0x43200000 via U-Boot's default load method
    # First check if host file is accessible
    sys.stdout.write("  Checking host file accessibility...\n"); sys.stdout.flush()
    resp = send_cmd(ser, "ext4size mmc 0:1 /stage", 2.0)
    print_lines(resp)
    
    # Use fatload workaround: since ext4load needs the file on SD,
    # we need to push the file somehow. Use the working approach:
    # Write directly to SD using a known working method.
    # Alternative: bypass boot.scr entirely and just fix bootcmd.
    sys.stdout.write("  Skipping file push (would need TFTP/HTTP server).\n"); sys.stdout.flush()
    sys.stdout.write("  Will use bootcmd workaround instead.\n"); sys.stdout.flush()
else:
    sys.stdout.write(f"  WARNING: {FIXED_BOOTSCR} not found!\n"); sys.stdout.flush()

# === SET DIRECT BOOTCMD ===
sys.stdout.write("\n=== Setting bootcmd ===\n"); sys.stdout.flush()
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
resp = send_cmd(ser, "saveenv", 5.0)
print_lines(resp)
resp = send_cmd(ser, "printenv bootcmd", 2.0)
print_lines(resp)

# === BOOT ===
sys.stdout.write(f"\n[{time.strftime('%H:%M:%S')}] === BOOTING ===\n"); sys.stdout.flush()
ser.write(b'boot\r')
time.sleep(2); drain(ser)

# === WATCH KERNEL ===
sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] Watching kernel (60s max)...\n"); sys.stdout.flush()
boot_start = time.time()
last_dot = boot_start
userspace = False
panic = False

while time.time() - boot_start < 60:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        decoded = data.decode('utf-8', errors='replace')
        sys.stdout.write(decoded); sys.stdout.flush()
        if 'Kernel panic' in decoded or 'BUG:' in decoded:
            panic = True
        if 'login:' in decoded:
            userspace = True
            sys.stdout.write(f"\n[USERSAPCE at +{time.time()-boot_start:.1f}s]!!!\n"); sys.stdout.flush()
    if time.time() - last_dot > 10:
        sys.stdout.write(f"  [{int(time.time()-boot_start)}s | u={userspace} p={panic}]\n"); sys.stdout.flush()
        last_dot = time.time()
    if userspace or panic:
        break
    time.sleep(0.05)

# Clean up
running = False
log_thread.join(timeout=2)
ser.close()

# === SSH CHECK ===
sys.stdout.write(f"\n[{time.strftime('%H:%M:%S')}] Checking SSH...\n"); sys.stdout.flush()
time.sleep(5)
ssh_ok = subprocess.run(["ping","-c","3","-W","2","192.168.0.151"], capture_output=True).returncode == 0

sys.stdout.write(f"\n{'='*60}\n")
sys.stdout.write(f"SSH={ssh_ok} userspace={userspace} panic={panic}\n")
sys.stdout.write(f"Log: {LOG}\n")
sys.stdout.write(f"{'='*60}\n")
sys.stdout.flush()
