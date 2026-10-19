#!/usr/bin/env python3
"""deploy_fixed_bootscr.py — Write boot.scr.465-fixed to /boot/boot.scr using mw.l + ext4write workaround.
The working sequence from sercap_go.log:
- boot.scr = boot.scr.465-fixed (6350 bytes)
- kernel_addr_r=0x41000000, ramdisk_addr_r=0x43300000, fdt_addr_r=0x43000000
- bootm 0x41000000 0x43300000 0x43000000
- kernel=/boot/uImage, initrd=/boot/uInitrd-6.18.19+, dtb=golden

Usage: sudo python3 deploy_fixed_bootscr.py
"""
import serial, sys, time, os, subprocess, base64

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/deploy_fixed_bootscr.log"

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

# Load 465-fixed into RAM
log("Loading boot.scr.465-fixed...")
resp = send_cmd(ser, "ext4load mmc 0:1 0x43200000 /boot/boot.scr.465-fixed", 10)
log(f"  Result: {resp.strip()[:100]}")

# Since ext4write fails with offset issue, let's try a different approach:
# 1. Create empty file with ext4write (offset 0, size 0)
log("Creating empty /boot/boot.scr...")
resp = send_cmd(ser, "ext4write mmc 0:1 0x43200000 /boot/boot.scr 0 0", 10)
log(f"  create: {resp.strip()[:100]}")

# 2. Now write the actual content (ext4write might work now that file exists)
log("Writing 465-fixed content (6350 bytes)...")
resp = send_cmd(ser, "ext4write mmc 0:1 0x43200000 /boot/boot.scr 0 6350", 15)
log(f"  write: {resp.strip()[:200]}")

# Verify size
resp = send_cmd(ser, "ext4size mmc 0:1 /boot/boot.scr", 5)
log(f"  verify: {resp.strip()}")

# Also fix bootcmd to use the correct addresses
log("Setting bootcmd for 465-fixed addresses...")
bootcmd = (
    "setenv bootcmd '"
    "ext4load mmc 0:1 0x41000000 /boot/uImage; "
    "ext4load mmc 0:1 0x43300000 /boot/uInitrd-6.18.19+; "
    "ext4load mmc 0:1 0x43000000 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015; "
    "ext4load mmc 0:1 0x45000000 /boot/dtb/allwinner/overlay/sun60i-a733-ili9486-spi.dtbo; "
    "fdt addr 0x43000000; fdt resize 65536; fdt apply 0x45000000; "
    "setenv bootargs console=ttyS0,115200 root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 "
    "rootwait rootfstype=ext4 modprobe.blacklist=aic8800_sdio,aic8800_bt "
    "loglevel=7 clk_ignore_unused earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000; "
    "bootm 0x41000000 0x43300000 0x43000000'"
)
send_cmd(ser, bootcmd, 3)
send_cmd(ser, "saveenv", 5)

# Boot with the new bootcmd
log("=== BOOTING with new bootcmd ===")
ser.write(b'boot\r')
time.sleep(3)
drain(ser)

log("Watching boot (180s)...")
boot_start = time.time()
userspace = False
while time.time() - boot_start < 180:
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