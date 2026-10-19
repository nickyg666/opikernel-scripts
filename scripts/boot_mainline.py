#!/usr/bin/env python3
"""
Clean mainline kernel boot with serial recovery.
FIXES (audited before deployment):
1. mainline 6.18 booti — aic8800_btlpm is BUILT-IN to vendor kernel, blacklist useless
2. setsid reader — survives parent SIGKILL, no os.close() fork bug
3. CDC-ACM rebind AFTER port reappears — path becomes stale after power cycle
4. distro_bootcmd fires TWICE — spam-break intercepts both
5. kill ALL stale before starting
6. inline bootargs only — no DTB patching (avoids FDT_ERR_NOSPACE on vendor DTB)
7. tries both DTB paths, proceeds on first success
"""
import subprocess, time, serial, sys, os, signal, socket

# Config
BOARD_IP = "192.168.0.151"
TTY = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/opikernel/pvrgl-work/boot_mainline.log"

# Mainline kernel (no aic8800_btlpm built-in)
# Addresses: kernel 0x41000000, initrd 0x43300000, DTB 0x43000000 (all below 0x4399999)
KERNEL_PATH = "/boot/mainline/Image"
INITRD_PATH = "/boot/mainline/initrd.img-6.18.19+"
# Try both DTB paths — use whichever exists on SD
DTB_PATHS = [
    "/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb",
    "/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015",
]

BOOTARGS = "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

# ── Step 1: Kill ALL stale port holders ──────────────────────────────────────
def kill_all_stale():
    result = subprocess.run(
        "ps aux | grep -E 'boot_|serial_.*py|cat.*ttyACM' | grep -v grep | awk '{print $2}'",
        shell=True, capture_output=True, text=True
    )
    pids = [p for p in result.stdout.strip().split() if p]
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
            log(f"Killed stale PID {pid}")
        except:
            pass
    time.sleep(1)

# ── Step 2: Background serial reader (setsid — survives parent SIGKILL) ─────
def start_reader():
    with open(LOG, "w") as f:
        f.write("")
    # setsid creates new session; reader becomes orphaned child of init, survives parent death
    p = subprocess.Popen(
        ["setsid", "bash", "-c",
         f"cat < {TTY} >> {LOG}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    log(f"Reader started PID={p.pid} (session leader={os.getsid(p.pid)})")
    time.sleep(1)
    return p.pid

# ── Step 3: CDC-ACM rebind (AFTER power cycle, AFTER port reappears) ───────────
def rebind_cdc_acm():
    """CDC-ACM FIFO state is stale after power cycle. Rebind to get fresh /dev/ttyACM0."""
    unbind = "/sys/bus/usb/drivers/cdc_acm/unbind"
    bind = "/sys/bus/usb/drivers/cdc_acm/bind"
    # Find the current USB path — enumerate all cdc_acm devices
    result = subprocess.run(
        "ls /sys/bus/usb/drivers/cdc_acm/ 2>/dev/null | head -5",
        shell=True, text=True
    )
    for dev in result.stdout.strip().split():
        if not dev or dev == "bind" or dev == "unbind":
            continue
        try:
            with open(unbind, "w") as f:
                f.write(dev)
            time.sleep(0.3)
            with open(bind, "w") as f:
                f.write(dev)
            time.sleep(0.5)
            log(f"CDC-ACM rebind OK: {dev}")
            return True
        except Exception as e:
            pass
    log("CDC-ACM rebind skipped (no path found)")
    return False

# ── Step 4: Power cycle ───────────────────────────────────────────────────────
def power_cycle():
    subprocess.run(["python3", "/home/host/smartplug.py", "off"], capture_output=True)
    time.sleep(8)
    subprocess.run(["python3", "/home/host/smartplug.py", "on"], capture_output=True)
    log("Power cycled")

# ── Step 5: Wait for ttyACM0 to reappear after USB enumeration ───────────────
def wait_for_port(timeout=30):
    for i in range(timeout):
        if os.path.exists(TTY):
            st = os.stat(TTY)
            if (st.st_mode & 0o170000) == 0o020000:  # real char device
                log(f"ttyACM0 appeared at T+{i}s — settling 2s")
                time.sleep(2)
                rebind_cdc_acm()
                time.sleep(1)
                return True
        time.sleep(1)
    log("ttyACM0 never appeared")
    return False

# ── Step 6: Intercept U-Boot shell ─────────────────────────────────────────────
# distro_bootcmd fires TWICE — must break during BOTH
def intercept_u_boot(s, deadline=None):
    if deadline is None:
        deadline = time.time() + 25
    in_shell = False
    buf = []
    while time.time() < deadline:
        if s.in_waiting:
            data = s.read(s.in_waiting)
            text = data.decode('latin-1', errors='replace')
            for line in text.split('\r\n'):
                line = line.strip()
                if line:
                    buf.append(line)
                    print(f"  {line}", flush=True)
            if '=> ' in text or 'Hit any key' in text or '# ' in text:
                in_shell = True
                break
        time.sleep(0.05)
    return in_shell

# ── Step 7: Spam BREAK to catch distro_bootcmd countdown ──────────────────────
def send_break_signal(s):
    """Hardware BREAK — U-Boot drops to shell regardless of countdown."""
    s.break_condition = True
    time.sleep(0.05)
    s.break_condition = False
    time.sleep(0.3)

def send_break_spam(s, count=15, delay=0.3):
    """Spam CR to catch any countdown."""
    for _ in range(count):
        s.write(b'\r')
        s.flush()
        time.sleep(delay)

def drain(s):
    while s.in_waiting:
        try:
            s.read(s.in_waiting)
        except:
            break

# ── Step 8: Check DTB exists on board SD ──────────────────────────────────────
def check_dtb_on_board(s):
    """Check which DTB paths exist on board SD via U-Boot."""
    for dtb in DTB_PATHS:
        s.reset_input_buffer()
        s.write(f"ext4ls mmc 0:1 {dtb}\n".encode())
        s.flush()
        time.sleep(2)
        buf = b''
        deadline = time.time() + 3
        while time.time() < deadline:
            if s.in_waiting:
                buf += s.read(s.in_waiting)
            time.sleep(0.05)
        text = buf.decode('latin-1', errors='replace')
        if '-rw-r--r--' in text or 'sun60i' in text:
            log(f"DTB found: {dtb}")
            return dtb
        else:
            log(f"DTB NOT found: {dtb}")
    return None

# ── Step 9: Mainline boot sequence ─────────────────────────────────────────────
def boot_mainline(s):
    # distro_bootcmd fires twice — send break spam to catch both
    log("Spamming BREAK to catch distro_bootcmd...")
    send_break_spam(s, count=20, delay=0.25)
    send_break_signal(s)
    time.sleep(1)
    drain(s)

    # Check if we're in shell
    s.write(b'\r')
    s.flush()
    time.sleep(1)
    if not intercept_u_boot(s, deadline=time.time() + 3):
        log("Could not confirm U-Boot shell — proceeding blind")

    # Check which DTB exists
    log("Checking DTB paths on SD...")
    dtb = check_dtb_on_board(s)
    if not dtb:
        log("WARNING: No DTB found — using default path anyway")

    # Build boot sequence
    K = KERNEL_PATH
    I = INITRD_PATH
    D = dtb or DTB_PATHS[0]
    A = BOOTARGS

    cmds = [
        ("setenv bootargs " + A, "bootargs set"),
        (f"ext4load mmc 0:1 0x41000000 {K}", "kernel loaded"),
        (f"ext4load mmc 0:1 0x43300000 {I}", "initrd loaded"),
        (f"ext4load mmc 0:1 0x43000000 {D}", "dtb loaded"),
        ("fdt addr 0x43000000", "fdt addr OK"),
        ("fdt resize 65536", "fdt resize OK"),
        (f"setenv bootargs {A}", "bootargs re-set"),
        ("booti 0x41000000 - 0x43000000", "BOOTING"),
    ]

    for cmd, label in cmds:
        log(f">>> {cmd[:80]}")
        s.write((cmd + '\r').encode())
        s.flush()
        time.sleep(2)
        # Drain response
        buf = b''
        deadline = time.time() + 5
        while time.time() < deadline:
            if s.in_waiting:
                buf += s.read(s.in_waiting)
            time.sleep(0.05)
        if buf:
            text = buf.decode('latin-1', errors='replace')
            for line in text.split('\r\n'):
                line = line.strip()
                if line:
                    print(f"  {line}", flush=True)
        if label == "BOOTING":
            break

    log("Kernel booting — monitoring output...")
    return True

# ── Step 10: Monitor for kernel boot + SSH ─────────────────────────────────────
def wait_for_ssh(timeout=180):
    deadline = time.time() + timeout
    log("Polling SSH...")
    while time.time() < deadline:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            r = sock.connect_ex((BOARD_IP, 22))
            sock.close()
            if r == 0:
                log(f"SSH UP at T+{int(time.time()-start_ts)}s!")
                return True
        except:
            pass
        time.sleep(5)
    return False

start_ts = time.time()

def main():
    log("=== CLEAN MAINLINE BOOT ===")
    log(f"TTY={TTY} BAUD={BAUD}")
    log(f"Board IP={BOARD_IP}")
    log(f"Kernel={KERNEL_PATH}")
    log(f"Initrd={INITRD_PATH}")
    log(f"DTB (try)={DTB_PATHS}")
    log(f"BOOTARGS={BOOTARGS}")
    print()

    # 1. Kill stale
    log("[1/7] Kill stale scripts...")
    kill_all_stale()

    # 2. Start reader FIRST
    log("[2/7] Start serial reader...")
    reader_pid = start_reader()

    # 3. Power cycle
    log("[3/7] Power cycle...")
    power_cycle()

    # 4. Wait for port
    log("[4/7] Wait for ttyACM0...")
    if not wait_for_port():
        log("FAIL: serial port never appeared")
        return 1

    # 5. Open serial, intercept U-Boot
    log("[5/7] Open serial, intercept U-Boot...")
    try:
        s = serial.Serial(TTY, BAUD, timeout=1)
        s.reset_input_buffer()
    except Exception as e:
        log(f"Serial open FAIL: {e}")
        return 1

    # distro_bootcmd fires TWICE — spam BREAK
    if not intercept_u_boot(s, deadline=time.time() + 20):
        log("U-Boot intercept timeout — try blind break")
        send_break_signal(s)
        time.sleep(2)
        drain(s)

    # 6. Boot mainline
    log("[6/7] Boot mainline kernel...")
    boot_mainline(s)

    # 7. Monitor SSH
    log("[7/7] Wait for SSH...")
    if wait_for_ssh(timeout=180):
        log("SUCCESS: Board online!")
        ssh_ok = False
        try:
            r = subprocess.run(
                ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
                 "-o", "ConnectTimeout=5", f"orangepi@{BOARD_IP}", "echo SSH_OK"],
                capture_output=True, text=True, timeout=10
            )
            ssh_ok = "SSH_OK" in r.stdout
        except:
            pass
        if ssh_ok:
            log("SSH CONFIRMED")
        else:
            log("SSH port open but auth failed — check credentials")
    else:
        elapsed = int(time.time() - start_ts)
        log(f"FAIL: SSH not up after {elapsed}s")
        log("Check serial log for kernel panic")

    log(f"Elapsed: {int(time.time()-start_ts)}s")
    s.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
