#!/usr/bin/env python3
"""boot_vendor_withinitrd.py — Vendor kernel + vendor initrd (both loaded), bootm NO initrd.
Matches sercap_vendor_repair.log: load initrd but don't pass to bootm (vendor kernel has built-in initrd).
Usage: sudo python3 boot_vendor_withinitrd.py
"""
import serial, sys, time, os, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/pvrgl-work/boot_vendor_withinitrd.log"

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

# VENDOR KERNEL + VENDOR INITRD (both loaded at addresses)
K = "/boot/uImage"
I = "/boot/uInitrd-6.6.98-sun60iw2"
D = "/boot/mainline/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015"
O = "/boot/dtb/allwinner/overlay/sun60i-a733-ili9486-spi.dtbo"

log("Load kernel uImage...")
send_cmd(ser, f"ext4load mmc 0:1 0x41000000 {K}", 20)
log("Load vendor initrd uImage...")
send_cmd(ser, f"ext4load mmc 0:1 0x43300000 /boot/uInitrd-6.6.98-sun60iw2", 30)
log("Load golden DTB...")
send_cmd(ser, f"ext4load mmc 0:1 0x43000000 {D}", 10)
log("Apply ili9486 overlay...")
send_cmd(ser, f"ext4load mmc 0:1 0x45000000 {O}", 10)
send_cmd(ser, "fdt addr 0x43000000", 3)
send_cmd(ser, "fdt resize 65536", 3)
send_cmd(ser, "fdt apply 0x45000000", 3)

ROOT_UUID = "442af407-cb84-48f8-845e-4be5cd18ce13"
A = f"console=ttyS0,115200 root=UUID={ROOT_UUID} rootwait rootfstype=ext4 modprobe.blacklist=aic8800_sdio,aic8800_bt loglevel=7 clk_ignore_unused earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000"
send_cmd(ser, f"setenv bootargs {A}", 3)

# BOOTM WITH NO INITRD (vendor kernel has built-in)
log("=== BOOTING with bootm (NO initrd in bootm, but initrd loaded at 0x43300000) ===")
send_cmd(ser, "bootm 0x41000000 - 0x43000000", 3)

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