#!/usr/bin/env python3
"""
recovery_clean_known_good.py

Boots board using PROVEN card-boot-20260830 memory layout:
- Image     at 0x41000000 (24.8MB → ends 0x42A00000, fits)
- DTB       at 0x43000000 (213KB → ends 0x43035000, fits)
- tiny-uInitrd at 0x43300000 (1.5MB → ends 0x43480000, fits below ATF 0x48000000)

boot.scr on SD is currently 0 bytes — fall back to manual ext4load + booti.
DTB is loaded FRESH from /boot/mainline/ (good one, 213801 bytes) — DTB stub at
/boot/dtb/allwinner/ is corrupted (165KB, missing FDT space for bootargs).

boardargs baked into U-Boot's setenv (NOT fdt patch — avoids FDT_ERR_NOSPACE).

SUCCESS CRITERIA: SSH to .138 or .151 within 120s of booti.
"""
import os
import sys
import time
import fcntl
import select
import signal
import subprocess
import threading

TTY = "/dev/ttyACM0"
LOG = "/home/host/opikernel/pvrgl-work/recovery_clean.log"
RDR = "/home/host/opikernel/pvrgl-work/recovery_clean_reader.log"
PLUG = "/home/host/smartplug.py"

# PROVEN layout — kernel/DTB/tiny fit in 0x41000000..0x43480000, well below ATF 0x48000000
IMAGE_PATH = "/boot/mainline/Image"              # 26048520 bytes (24.8MB)
DTB_PATH   = "/boot/mainline/sun60i-a733-orangepi-zero3w.dtb"  # 213801 bytes (good)
INITRD_PATH = "/boot/mainline/tiny-uInitrd"      # 1601510 bytes (1.5MB) — busybox initramfs

# bootargs: NO aic8800 in Image; blacklist anyway for safety
BOOTARGS = (
    "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 "
    "rootwait rootfstype=ext4 "
    "console=ttyS0,115200 earlyprintk "
    "loglevel=7 swiotlb=65536 ipv6.disable=1"
)

# A733 U-Boot 2018 32-bit: max initrd addr = 0x4399999
IMG_ADDR  = "0x41000000"
DTB_ADDR  = "0x43000000"
RD_ADDR   = "0x43300000"

def log(s):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {s}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def kill_stale():
    for p in subprocess.run(["sudo", "lsof", "-t", TTY], capture_output=True, text=True).stdout.split():
        try: os.kill(int(p), 9)
        except: pass
    for n in ["boot_clean", "boot_v", "boot_mainline", "boot_recover", "recovery_0830",
              "recover_v2", "recover_v3", "sercap", "boot_fast", "boot_final",
              "boot_one", "boot_ssh", "boot_robust", "boot_verbose", "boot_threaded",
              "boot_auto", "boot_unified", "boot_vendor", "boot_slow", "boot_break",
              "boot_bare", "boot_c", "boot_diag", "boot_direct", "boot_combo",
              "boot_exact", "boot_complete", "boot_persist", "boot_fg"]:
        subprocess.run(["pkill", "-9", "-f", n], capture_output=True)
    time.sleep(1)
    log("Stale cleared")

def cdc_reset():
    subprocess.run(["sudo", "modprobe", "-r", "cdc_acm"], capture_output=True)
    time.sleep(2)
    subprocess.run(["sudo", "modprobe",    "cdc_acm"], capture_output=True)
    time.sleep(3)
    log("CDC-ACM reset done")

def power_cycle():
    log("Power off opiz3w")
    subprocess.run(["python3", PLUG, "off"], capture_output=True)
    time.sleep(8)
    log("Power on opiz3w")
    subprocess.run(["python3", PLUG, "on"], capture_output=True)
    time.sleep(4)

def open_port():
    # Try open up to 10 times
    for i in range(10):
        try:
            return os.open(TTY, os.O_RDWR | os.O_NOCTTY)
        except OSError as e:
            log(f"  open {TTY} attempt {i+1}: {e}")
            time.sleep(1)
    raise RuntimeError("can't open TTY")

def send(fd, cmd, wait=2.0):
    os.write(fd, (cmd + "\r").encode())
    time.sleep(wait)

def drain(fd):
    """Drain stale bytes quickly."""
    end = time.time() + 0.3
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try: os.read(fd, 4096)
            except: pass
        else: break

def main():
    open(LOG, "w").write(f"# recovery_clean {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    open(RDR, "w").write("")

    kill_stale()
    power_cycle()
    cdc_reset()

    # Background reader
    rp = os.fork()
    if rp == 0:
        os.setsid()
        for attempt in range(30):
            try:
                fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
                f = open(RDR, "ab", 0)
                while True:
                    r,_,_ = select.select([fd], [], [], 1)
                    if r:
                        d = os.read(fd, 4096)
                        if d: f.write(d)
                    else: time.sleep(0.05)
            except OSError:
                time.sleep(1)
        os._exit(0)
    log(f"Reader PID={rp}")
    time.sleep(1)

    fd = open_port()
    log("TTY open")

    # Break to U-Boot
    log("Sending 250x CR to catch U-Boot prompt")
    for _ in range(250):
        try: os.write(fd, b"\r")
        except: pass
        time.sleep(0.04)
    time.sleep(2)
    drain(fd)

    # === BOOT SEQUENCE: clean known-good layout ===
    log(f"1. Load {IMAGE_PATH} → {IMG_ADDR}")
    send(fd, f"ext4load mmc 0:1 {IMG_ADDR} {IMAGE_PATH}", wait=20)

    log(f"2. Load {DTB_PATH} → {DTB_ADDR}")
    send(fd, f"ext4load mmc 0:1 {DTB_ADDR} {DTB_PATH}", wait=5)

    log(f"3. Load {INITRD_PATH} → {RD_ADDR}")
    send(fd, f"ext4load mmc 0:1 {RD_ADDR} {INITRD_PATH}", wait=3)

    log("4. setenv bootargs (no fdt patch — avoids FDT_ERR_NOSPACE)")
    send(fd, f"setenv bootargs '{BOOTARGS}'", wait=2)

    log(f"5. booti {IMG_ADDR} {RD_ADDR} {DTB_ADDR}")
    send(fd, f"booti {IMG_ADDR} {RD_ADDR} {DTB_ADDR}", wait=3)

    # Don't close the FD — the reader still owns the port. Just exit.
    try: os.close(fd)
    except: pass

    # Wait for SSH
    log("Waiting up to 120s for kernel boot + SSH")
    for i in range(24):
        time.sleep(5)
        for ip in ("192.168.0.151", "192.168.0.138"):
            r = subprocess.run(
                ["sshpass", "-p", "orangepi", "ssh",
                 "-o", "StrictHostKeyChecking=accept-new",
                 "-o", "ConnectTimeout=2",
                 f"orangepi@{ip}", "echo ONLINE; uname -r"],
                capture_output=True, text=True, timeout=8
            )
            if "ONLINE" in r.stdout:
                log(f"*** BOARD ONLINE at {ip}: {r.stdout.strip()} ***")
                subprocess.run(["pkill", "-9", "-P", str(os.getpid())], capture_output=True)
                os.kill(rp, 9)
                return 0
        log(f"  T+{(i+1)*5}s: not yet")

    log("SSH never came up. Reader tail:")
    subprocess.run(["tail", "-c", "3000", RDR], capture_output=False)
    os.kill(rp, 9)
    return 1

if __name__ == "__main__":
    sys.exit(main())
