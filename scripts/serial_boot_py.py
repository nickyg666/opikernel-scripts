#!/usr/bin/env python3
"""Serial boot + U-Boot intercept + SSH verify. Uses setsid cat background logger."""
import datetime, os, subprocess, sys, time

PORT = "/dev/ttyACM1"
LOG_DIR = "/home/host/opikernel/pvrgl-work"
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, f"boot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
BOARD = "192.168.0.151"

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def ssh_check(timeout=8):
    try:
        r = subprocess.run(
            ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=" + str(timeout), f"orangepi@{BOARD}", "echo SSH_OK"],
            capture_output=True, text=True, timeout=timeout + 2
        )
        return "SSH_OK" in r.stdout
    except Exception:
        return False

def send_break():
    """Send spaces to break into U-Boot."""
    with open(PORT, "wb") as f:
        f.write(b"        \n")
        f.flush()

def send_cmd(cmd):
    """Send command to serial port."""
    with open(PORT, "wb") as f:
        f.write((cmd + "\n").encode())
        f.flush()
    time.sleep(0.5)

def read_log_marker(marker, timeout=30):
    """Poll log file for marker text."""
    start = time.time()
    last_pos = 0
    while time.time() - start < timeout:
        time.sleep(0.3)
        try:
            with open(LOG, "rb") as f:
                f.seek(last_pos)
                data = f.read()
                last_pos = f.tell()
            if marker.encode() in data:
                return True
        except Exception:
            pass
    return False

def cat_logger_alive():
    """Check if cat is capturing data by seeing if log file is growing."""
    try:
        mtime = os.path.getmtime(LOG)
        return (time.time() - mtime) < 2  # Modified within last 2s
    except Exception:
        return False

log(f"=== Boot sequence starting ===")
log(f"Log: {LOG}")

# Eject any competing port holders
subprocess.run(["fuser", "-k", PORT], capture_output=True)
time.sleep(0.5)

# Start setsid cat as background logger
# setsid forks and exits; cat stays alive as orphaned child in new session
subprocess.Popen(
    ["setsid", "bash", "-c", f"cat < {PORT} >> {LOG}"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    start_new_session=True
)
log("Background cat started")
time.sleep(2)

# Verify log is growing
if cat_logger_alive():
    log("Logger is alive and capturing")
else:
    log("WARNING: Logger may not be capturing — continuing anyway")

log("Powering off board...")
r = subprocess.run(["python3", "/home/host/smartplug.py", "off"], capture_output=True, text=True)
log(f"  off: {r.stdout.strip()}")
time.sleep(9)

log("Powering on board...")
r = subprocess.run(["python3", "/home/host/smartplug.py", "on"], capture_output=True, text=True)
log(f"  on: {r.stdout.strip()}")

# U-Boot timeline:
# T+0: power on
# T+1.5: BOOT0 starts (HW init)
# T+5: BOOT0 ends, U-Boot starts
# T+6: "Hit any key to stop autoboot:  1" (1-second countdown)
# T+7: U-Boot autoboot triggers
# Send break at T+5.5 (just before countdown) — spaces will be buffered until U-Boot starts
log("Sending break at T+5.5s...")
time.sleep(5.5)
send_break()

# Wait for U-Boot countdown to expire, then we're at the prompt
log("Waiting 3s for U-Boot to reach '=> ' prompt...")
time.sleep(3)

# Verify serial output is happening
if cat_logger_alive():
    log("Logger still alive — serial output confirmed")
else:
    log("WARNING: Logger died — serial output may be missing")

# We're at the U-Boot prompt. Send the proven boot sequence.
# NO waiting for "=>" marker — we know we're there from timing.

log("Setting bootargs (aic8800_btlpm blacklisted)...")
send_cmd("setenv bootargs root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_bt console=ttyS0,115200 aic8800_bt.disable=1")

log("Loading kernel (26MB, ~30s)...")
send_cmd("ext4load mmc 0:1 0x41000000 boot/uImage")
time.sleep(35)  # 26MB uImage load

log("Loading DTB (~3s)...")
send_cmd("ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb")
time.sleep(5)

log("Booting vendor kernel...")
send_cmd("bootm 0x41000000 - 0x43000000")

# Kernel boot: poll for login
log("Waiting for login prompt (~90s)...")
found = read_log_marker("login:", timeout=100)
if found:
    log("Login prompt detected!")
    time.sleep(10)
    if ssh_check():
        log("SUCCESS: Board reachable at .151!")
    else:
        time.sleep(15)
        if ssh_check():
            log("SUCCESS: Board reachable at .151!")
        else:
            log("WARNING: SSH failing")
else:
    # Diagnose
    with open(LOG, "rb") as f:
        data = f.read()
    d = data.decode("utf-8", errors="replace")
    # Find kernel timestamps (T+60 onwards)
    lines = [l for l in d.split("\n") if l.strip()]
    kernel_lines = [l for l in lines if l.startswith("[") and "]" in l[:15]]
    if kernel_lines:
        log(f"Last kernel output: {repr(kernel_lines[-5:])}")
    if "panic" in d.lower() or "oops" in d.lower():
        log("KERNEL PANIC DETECTED")
    if ssh_check(timeout=5):
        log("SUCCESS: Board reachable at .151!")
    else:
        log("WARNING: SSH not reachable")

log("Done. Serial log: " + LOG)
