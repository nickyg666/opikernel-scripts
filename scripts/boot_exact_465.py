#!/usr/bin/env python3
"""boot_exact_465.py — Execute the EXACT boot sequence from boot.scr.465-fixed.
The script uses:
- kernel at 0x41000000 (uImage: /boot/mainline/Image)
- ramdisk at 0x45000000 (RAW gzip: /boot/mainline/tiny-uInitrd)
- DTB at 0x44000000 (/boot/mainline/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015)
- il 9486 overlay applied via fdt apply
- booti to launch kernel

Plus aic8800 blacklist added to bootargs.
Usage: sudo python3 boot_exact_465.py
"""
import serial, sys, time, os, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/boot_exact_465.log"

logf = open(LOG, 'wb', buffering=0)
def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}\n"
    sys.stdout.write(line); sys.stdout.flush()
    logf.write(line.encode('utf-8')); logf.flush()

def drain(ser):
    for _ in range(20):
        if ser.in_waiting:
            ser.read(ser.in_waiting)
        time.sleep(0.1)

def send_cmd(ser, cmd, wait=3.0):
    ser.write(cmd.encode() + b'\r')
    time.sleep(0.1)
    out = b''
    deadline = time.time() + wait
    while time.time() < deadline:
        if ser.in_waiting:
            out += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return out.decode('utf-8', errors='replace')

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

log("Killing readers...")
subprocess.run("sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1", shell=True)
time.sleep(2)

log("Opening serial...")
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False; ser.rts = False
time.sleep(0.5)
drain(ser)

log("Power cycle...")
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","off","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
time.sleep(5)
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","on","--model","WLPP1CFH","D03F271583AE"], capture_output=True)

log("Waiting for U-Boot...")
pat, _ = wait_for(ser, ['Hit any key', '=>'], timeout=30)
if not pat:
    log("FAILED: No prompt"); logf.close(); ser.close(); sys.exit(1)
log(f"Found '{pat}' — break...")
ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
time.sleep(0.3); ser.write(b'\r'); time.sleep(1.0)
drain(ser); time.sleep(2)

# EXACT boot.scr.465-fixed sequence:
# Set addresses first
log("Setting addresses...")
send_cmd(ser, "setenv kernel_addr_r 0x41000000", 2)
send_cmd(ser, "setenv fdt_addr_r 0x44000000", 2)
send_cmd(ser, "setenv ramdisk_addr_r 0x45000000", 2)
send_cmd(ser, "setenv load_addr 0x46000000", 2)

# Load kernel (uImage format, but bootm=uImage+booti hybrid works)
log("Load kernel...")
send_cmd(ser, "ext4load mmc 0:1 0x41000000 /boot/mainline/Image", 20)

# Load DTB (golden)
log("Load DTB...")
send_cmd(ser, "ext4load mmc 0:1 0x44000000 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015", 10)

# fdt addr + resize
send_cmd(ser, "fdt addr 0x44000000", 3)
send_cmd(ser, "fdt resize 65536", 3)

# Load overlay
log("Load ili9486 overlay...")
send_cmd(ser, "ext4load mmc 0:1 0x45000000 /boot/dtb/allwinner/overlay/sun60i-a733-ili9486-spi.dtbo", 10)
send_cmd(ser, "fdt apply 0x45000000", 3)

# Load initrd (RAW gzip at 0x45000000, but wait we just used that for overlay!)
# Re-load initrd at 0x46000000, then move it. Actually 465-fixed uses 0x45000000 for initrd
# and applies overlay before. Let me re-read.

# Re-load DTB to reset, then do the proper sequence
# Actually we need to redo: reload DTB after overlay apply
# Let me reset properly
log("Reloading DTB to reset state...")
send_cmd(ser, "ext4load mmc 0:1 0x44000000 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015", 10)
send_cmd(ser, "fdt addr 0x44000000", 3)
send_cmd(ser, "fdt resize 65536", 3)

# Apply overlay
log("Apply ili9486 overlay...")
send_cmd(ser, "fdt apply 0x45000000", 3)

# Load initrd into 0x45000000 (overlay area is now consumed)
log("Load initrd (tiny-uInitrd RAW gzip)...")
send_cmd(ser, "ext4load mmc 0:1 0x45000000 /boot/mainline/tiny-uInitrd", 10)

# Set bootargs with aic8800 blacklist - use correct root UUID
ROOT_UUID = "442af407-cb84-48f8-845e-4be5cd18ce13"
A = f"console=ttyS0,115200 root=UUID={ROOT_UUID} rootwait rootfstype=ext4 modprobe.blacklist=aic8800_sdio,aic8800_bt loglevel=7 clk_ignore_unused earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000"
log(f"Set bootargs: {A[:80]}")
send_cmd(ser, f"setenv bootargs {A}", 3)

# BOOTI!
log("=== BOOTING with booti ===")
send_cmd(ser, "booti 0x41000000 0x45000000 0x44000000", 3)

# Watch boot
log("Watching (90s)...")
boot_start = time.time()
userspace = False
while time.time() - boot_start < 90:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        decoded = data.decode('utf-8', errors='replace')
        logf.write(decoded.encode('utf-8', errors='replace')); logf.flush()
        if 'login:' in decoded:
            userspace = True; log("*** USERSAPCE ***"); break
        if 'Kernel panic' in decoded:
            log("*** PANIC ***"); break
    time.sleep(0.05)

logf.close(); ser.close()
time.sleep(5)
ssh_ok = subprocess.run(["ping","-c","3","-W","2","192.168.0.151"], capture_output=True).returncode == 0
log(f"\nRESULT: SSH={ssh_ok} userspace={userspace}")
log(f"Log: {LOG} ({os.path.getsize(LOG)} bytes)")
