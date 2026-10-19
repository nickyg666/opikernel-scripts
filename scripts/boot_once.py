#!/usr/bin/env python3
"""Single-shot mainline boot. Runs completely in background, no subprocess calls."""
import time, serial, sys, os, signal, socket

TTY = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/opikernel/pvrgl-work/boot_once.log"
BOARD_IP = "192.168.0.151"
KERNEL = "/boot/mainline/Image"
INITRD = "/boot/mainline/initrd.img-6.18.19+"
DTB = "/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb"
BOOTARGS = "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line, end='', flush=True)
    open(LOG, "a").write(line)

def kill_stale():
    import signal
    for pid_str in os.popen("ps aux | grep 'boot_\\|serial_\\|ttyACM' | grep -v grep | awk '{print $2}'").read().split():
        try: os.kill(int(pid_str), signal.SIGKILL)
        except: pass
    time.sleep(1)

def start_reader():
    with open(LOG, "w") as f: f.write("")
    pid = os.fork()
    if pid == 0:
        os.setsid()
        fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
        out = open(LOG, "ab", buffering=0)
        while True:
            r = os.read(fd, 4096)
            if r: out.write(r); out.flush()
            else: time.sleep(0.1)
    log(f"Reader PID={pid}\n")
    time.sleep(1)
    return pid

def power_cycle():
    os.system("/home/host/smartplug.py off")
    time.sleep(8)
    os.system("/home/host/smartplug.py on")
    log("Power cycled\n")

def wait_port():
    for i in range(30):
        if os.path.exists(TTY):
            st = os.stat(TTY)
            if (st.st_mode & 0o170000) == 0o020000:
                log(f"Port at T+{i}s, settle 3s\n")
                time.sleep(3)
                return True
        time.sleep(1)
    return False

def drain(s):
    while s.in_waiting: s.read(s.in_waiting)

def send(s, cmd, wait=2):
    s.write((cmd + "\r").encode())
    s.flush()
    time.sleep(wait)
    buf = b''
    dl = time.time() + wait + 1
    while time.time() < dl:
        if s.in_waiting: buf += s.read(s.in_waiting)
        time.sleep(0.05)
    return buf.decode('latin-1', errors='replace')

def intercept(s):
    dl = time.time() + 20
    while time.time() < dl:
        if s.in_waiting:
            d = s.read(s.in_waiting)
            t = d.decode('latin-1', errors='replace')
            for l in t.split('\r\n'):
                if l.strip(): print(f"  {l}", flush=True)
            if '=> ' in t or 'Hit any' in t: return True
        time.sleep(0.05)
    return False

def main():
    log("=== BOOT_ONCE ===\n")
    kill_stale()
    pid = start_reader()
    power_cycle()
    if not wait_port():
        log("FAIL: no port\n"); return 1
    try:
        s = serial.Serial(TTY, BAUD, timeout=1)
        s.reset_input_buffer()
    except Exception as e:
        log(f"Serial fail: {e}\n"); return 1

    # Spam BREAK to catch distro_bootcmd
    log("Break spam...\n")
    for _ in range(20):
        s.write(b'\r'); s.flush(); time.sleep(0.25)
    s.break_condition = True; time.sleep(0.05); s.break_condition = False
    time.sleep(1); drain(s)
    if not intercept(s):
        log("No U-Boot prompt — proceed blind\n")
        s.write(b'\r'); s.flush(); time.sleep(1); drain(s)

    # Boot sequence
    log("bootargs...\n"); send(s, f"setenv bootargs {BOOTARGS}", 1)
    log("kernel...\n"); send(s, f"ext4load mmc 0:1 0x41000000 {KERNEL}", 45)
    log("initrd...\n"); send(s, f"ext4load mmc 0:1 0x43300000 {INITRD}", 60)
    log("dtb...\n"); send(s, f"ext4load mmc 0:1 0x43000000 {DTB}", 5)
    log("fdt addr...\n"); send(s, "fdt addr 0x43000000", 1)
    log("fdt resize...\n"); send(s, "fdt resize 65536", 1)
    log("booti...\n"); send(s, "booti 0x41000000 - 0x43000000", 5)
    s.close()
    log("Booting — poll SSH for 300s...\n")

    # Poll SSH
    start = time.time()
    for i in range(60):
        time.sleep(5)
        try:
            sock = socket.socket(); sock.settimeout(2)
            if sock.connect_ex((BOARD_IP, 22)) == 0:
                sock.close()
                log(f"SSH UP at T+{int(time.time()-start)}s\n")
                return 0
        except: pass
        if i % 6 == 0: log(f"  ~{int(time.time()-start)}s elapsed...\n")
    log(f"FAIL after {int(time.time()-start)}s\n")
    return 1

sys.exit(main())
