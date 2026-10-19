#!/usr/bin/env python3
"""Boot daemon: os.fork() serial reader + power cycle + U-Boot intercept + SSH verify."""
import os, signal, socket, subprocess, sys, time

DEV = "/dev/ttyACM1"
LOG = "/home/host/pvrgl-work/boot_daemon2.log"
BOARD = "192.168.0.151"

def log(msg):
    ts = time.strftime("%H:%M:%S")
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
    with open(DEV, "wb") as f:
        f.write(b"        \r")
        f.flush()

def send_cmd(cmd):
    with open(DEV, "wb") as f:
        f.write((cmd + "\r").encode())
        f.flush()
    time.sleep(0.3)

def spam_enter(n=20):
    for _ in range(n):
        with open(DEV, "wb") as f:
            f.write(b"\r")
        time.sleep(0.25)

# === DAEMON CHILD ===
if len(sys.argv) == 2 and sys.argv[1] == "daemon":
    # Child: read serial to log file forever
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    with open(LOG, "wb") as f:
        with open(DEV, "rb") as ser:
            while True:
                data = ser.read(4096)
                if data:
                    f.write(data)
                    f.flush()
                else:
                    time.sleep(0.1)
    sys.exit(0)

# === PARENT ===
log("=== Boot sequence starting ===")
log(f"Log: {LOG}")

# Fork daemon child
pid = os.fork()
if pid == 0:
    # Child — become reader daemon
    os.setsid()
    os.close(0); os.close(1); os.close(2)
    with open(LOG, "wb") as f:
        with open(DEV, "rb") as ser:
            while True:
                data = ser.read(4096)
                if data:
                    f.write(data); f.flush()
                else:
                    time.sleep(0.1)
    sys.exit(0)

# Parent
log(f"Daemon child PID={pid}")
time.sleep(2)
# Verify child is alive
result = os.waitpid(pid, os.WNOHANG)
log(f"Daemon status: {'ALIVE' if result[0] == 0 else f'DIED {result}'}")

# Power cycle
log("Powering off...")
r = subprocess.run(["python3", "/home/host/smartplug.py", "off"], capture_output=True, text=True)
log(f"  off: {r.stdout.strip()}")
time.sleep(9)
log("Powering on...")
r = subprocess.run(["python3", "/home/host/smartplug.py", "on"], capture_output=True, text=True)
log(f"  on: {r.stdout.strip()}")

# U-Boot timing:
# T+0: power on
# T+5: BOOT0 ends, U-Boot starts  
# T+6: countdown "Hit any key" (1s)
# T+7: autoboot fires
# Break at T+5.5, wait until T+9 for prompt
log("Waiting for U-Boot boot messages...")
time.sleep(5.5)
send_break()
time.sleep(3.5)  # Now at T+9, U-Boot prompt ready

log("Sending break (extra)...")
spam_enter(10)

# Now at U-Boot prompt. Check serial log for evidence of capture
log("Sending boot commands...")
log("  bootargs...")
send_cmd("setenv bootargs root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_bt console=ttyS0,115200 aic8800_bt.disable=1")
time.sleep(1)
log("  ext4load kernel...")
send_cmd("ext4load mmc 0:1 0x41000000 boot/uImage")
time.sleep(35)  # 26MB
log("  ext4load dtb...")
send_cmd("ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb")
time.sleep(5)
log("  bootm...")
send_cmd("bootm 0x41000000 - 0x43000000")
time.sleep(2)

# Monitor kernel boot: poll log for login or panic
log("Monitoring kernel boot (~90s)...")
start = time.time()
login_seen = False
kernel_started = False
while time.time() - start < 100:
    time.sleep(2)
    # Check log file
    try:
        with open(LOG, "rb") as f:
            data = f.read()
        text = data.decode("latin-1", errors="replace")
        
        # Detect kernel boot
        for marker in ["Starting kernel", "Booting Linux", "[    0.", "login:", "login:"]:
            if marker in text:
                login_seen = True
                log(f"Login detected!")
                break
        for marker in ["Starting kernel", "Booting Linux", "[    0."]:
            if marker in text:
                kernel_started = True
        
        # Detect panic
        lower = text.lower()
        if "panic" in lower or "oops" in lower:
            log(f"PANIC DETECTED in log!")
            log(f"Last 500 chars: {repr(text[-500:])}")
            break
        
        if login_seen:
            break
    except Exception as e:
        log(f"Log read error: {e}")

if login_seen:
    time.sleep(10)
    if ssh_check():
        log("SUCCESS: Board at .151!")
    else:
        time.sleep(15)
        if ssh_check():
            log("SUCCESS: Board at .151!")
        else:
            log("Login seen but SSH failing")
elif kernel_started:
    log("Kernel booting — waiting more...")
    time.sleep(60)
    if ssh_check():
        log("SUCCESS: Board at .151!")
    else:
        log("Kernel started but SSH not ready")
else:
    with open(LOG, "rb") as f:
        data = f.read()
    text = data.decode("latin-1", errors="replace")
    log(f"No login or kernel start. Last 500 chars:")
    log(repr(text[-500:]))
    if ssh_check(timeout=5):
        log("SUCCESS: Board at .151!")
    else:
        log("Board not reachable via SSH")

log("=== DONE ===")
# Kill daemon child
try:
    os.kill(pid, 9)
except:
    pass
