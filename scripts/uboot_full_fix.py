#!/usr/bin/env python3
"""uboot_full_fix.py — Full board recovery via U-Boot:
1. Intercept U-Boot prompt
2. ext4write fixed boot.scr to SD
3. Set correct bootcmd to boot directly (bypass boot.scr)
4. Boot with working DTB + aic8800 blacklisted
"""
import serial, sys, time, signal, subprocess, os

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/uboot_full_fix.log"
BG_LOG = "/home/host/pvrgl-work/uboot_full_fix_bg.log"

def signal_handler(sig, frame):
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

def send_cmd(ser, cmd, wait=2.0, echo=True):
    if echo:
        print(f"  >>> {cmd[:80]}")
    ser.write(cmd.encode() + b'\r')
    time.sleep(0.1)
    out = b''
    deadline = time.time() + wait
    while time.time() < deadline:
        if ser.in_waiting:
            out += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return out.decode('utf-8', errors='replace')

# Kill existing readers
subprocess.run("sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1", shell=True)

# Start background logger (child process)
pid = os.fork()
if pid == 0:
    os.close(0); os.close(1); os.close(2)
    os.open('/dev/null', os.O_RDONLY)
    os.open('/dev/null', os.O_WRONLY)
    os.open('/dev/null', os.O_WRONLY)
    child_ser = serial.Serial(DEV, BAUD, timeout=1)
    with open(BG_LOG, 'wb') as lf:
        while True:
            if child_ser.in_waiting:
                data = child_ser.read(child_ser.in_waiting)
                lf.write(data); lf.flush()
            time.sleep(0.05)
    sys.exit(0)
time.sleep(1)

# Open foreground serial
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False; ser.rts = False
time.sleep(0.5)
drain(ser)

# Power cycle
print(f"[{time.strftime('%H:%M:%S')}] Power cycling...")
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","off","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
time.sleep(5)
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","on","--model","WLPP1CFH","D03F271583AE"], capture_output=True)

# Wait for U-Boot
print(f"[{time.strftime('%H:%M:%S')}] Waiting for U-Boot...")
start = time.time()
while time.time() - start < 30:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        decoded = data.decode('utf-8', errors='replace')
        print(decoded, end='', flush=True)
        if 'Hit any key' in decoded:
            print(f"\n[PROMPT at +{time.time()-start:.1f}s] Sending break...")
            ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
            time.sleep(0.3); ser.write(b'\r'); time.sleep(1.0)
            drain(ser)
            break
        elif '=>' in decoded:
            break
    time.sleep(0.05)

time.sleep(2); drain(ser)
print(f"\n[{time.strftime('%H:%M:%S')}] U-Boot shell ready.\n")

# === FIX: Write boot.scr.nofix to SD via ext4write ===
# First: verify SD card accessible and find the right DTB
checks = [
    ("mmcinfo", 3.0),
    ("ext4size mmc 0:1 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb", 3.0),
    ("ext4size mmc 0:1 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb.bak-current", 3.0),
    ("ext4size mmc 0:1 /boot/boot.scr", 3.0),
]

for cmd, wait in checks:
    print(f">>> {cmd}")
    resp = send_cmd(ser, cmd, wait)
    for line in resp.split('\r'):
        line = line.strip()
        if line and '=>' not in line:
            print(f"    {line}")
    time.sleep(0.3)

# === WRITE FIXED BOOT.SCR ===
# Load fixed boot.scr.nofix into memory at 0x43200000
print("\n=== Writing fixed boot.scr.nofix to SD ===")
print("Loading boot.scr.nofix into RAM...")
load_cmd = 'ext4load mmc 0:1 0x43200000 /stage/boot.scr.nofix'
print(f">>> {load_cmd}")
ser.write(load_cmd.encode() + b'\r')
time.sleep(3.0)
# Read response
out = b''
for _ in range(40):
    if ser.in_waiting:
        out += ser.read(ser.in_waiting)
    time.sleep(0.1)
decoded = out.decode('utf-8', errors='replace')
for line in decoded.split('\r'):
    line = line.strip()
    if line and '=>' not in line:
        print(f"    {line}")
# Check for success
if 'bytes loaded' in decoded or 'loaded' in decoded.lower():
    print("  [LOAD OK]")
else:
    print("  [LOAD FAILED - check path]")
    print(f"  Full response: {decoded[:500]}")

time.sleep(1)

# Write to /boot/boot.scr
print("Writing to /boot/boot.scr...")
write_cmd = 'ext4write mmc 0:1 0x43200000 /boot/boot.scr 0x00000e00'
print(f">>> {write_cmd}")
ser.write(write_cmd.encode() + b'\r')
time.sleep(3.0)
out = b''
for _ in range(40):
    if ser.in_waiting:
        out += ser.read(ser.in_waiting)
    time.sleep(0.1)
decoded = out.decode('utf-8', errors='replace')
for line in decoded.split('\r'):
    line = line.strip()
    if line and '=>' not in line:
        print(f"    {line}")
if 'bytes written' in decoded:
    print("  [WRITE OK]")
time.sleep(1)

# === SET BOOTCMD to bypass boot.scr and boot directly ===
print("\n=== Setting bootcmd to boot directly ===")
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
print(f">>> {bootcmd[:100]}...")
send_cmd(ser, bootcmd, 3.0)

# Save env
print(">>> saveenv")
send_cmd(ser, "saveenv", 5.0)

# Verify
print(">>> printenv bootcmd")
resp = send_cmd(ser, "printenv bootcmd", 2.0)
print(resp)

# === BOOT ===
print(f"\n[{time.strftime('%H:%M:%S')}] BOOTING KERNEL...")
send_cmd(ser, "boot", 2.0)

# Drain initial output
time.sleep(3)
drain(ser)

# Watch kernel boot
print(f"[{time.strftime('%H:%M:%S')}] Watching kernel boot (60s)...")
boot_start = time.time()
last_dot = boot_start
userspace = False
panic = False
aic8800_issue = False

while time.time() - boot_start < 90:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        decoded = data.decode('utf-8', errors='replace')
        print(decoded, end='', flush=True)
        
        if 'Kernel panic' in decoded or 'BUG:' in decoded:
            panic = True
        if 'login:' in decoded:
            userspace = True
            print(f"\n[USESPACE at +{time.time()-boot_start:.1f}s]!!!")
        if 'aic8800' in decoded.lower() and any(x in decoded.lower() for x in ['error','oops','bug','failed','panic']):
            aic8800_issue = True
            print(f"\n[aic8800 issue detected]")
    
    if time.time() - last_dot > 15:
        elapsed = int(time.time() - boot_start)
        print(f"  [{elapsed}s | userspace={userspace} panic={panic}]", flush=True)
        last_dot = time.time()
    
    if userspace:
        break
    time.sleep(0.05)

ser.close()

# SSH check
print(f"\n[{time.strftime('%H:%M:%S')}] Checking SSH...")
time.sleep(5)
ssh_ok = subprocess.run(["ping","-c","3","-W","2","192.168.0.151"], capture_output=True).returncode == 0

print(f"\n{'='*60}")
print(f"RESULT: SSH={ssh_ok} userspace={userspace} panic={panic}")
print(f"Background log: {BG_LOG}")
print(f"{'='*60}")
