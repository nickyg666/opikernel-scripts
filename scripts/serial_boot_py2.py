#!/usr/bin/env python3
"""Serial boot v5: proper command sending (no char drop), retry bootm."""
import sys, time, os, serial, threading

DEV = "/dev/ttyACM0"
LOG = "/home/host/pvrgl-work/sercap_pyboot2.log"
BAUD = 115200

open(LOG, 'w').close()

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')

class SerialReader:
    def __init__(self, ser, log_path):
        self.ser = ser
        self.log_path = log_path
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _read(self):
        while self.running:
            if self.ser.in_waiting:
                data = self.ser.read(self.ser.in_waiting)
                with open(self.log_path, 'ab') as f:
                    f.write(data)
            time.sleep(0.05)

    def size(self):
        return os.path.getsize(self.log_path)

    def drain(self, timeout=3):
        """Drain all available bytes, return as string."""
        deadline = time.time() + timeout
        buf = b''
        while time.time() < deadline:
            if self.ser.in_waiting:
                buf += self.ser.read(self.ser.in_waiting)
            time.sleep(0.1)
        return buf.decode('utf-8', errors='replace')

def send_cmd(ser, reader, cmd, wait_before=0.5, wait_after=2):
    """Send command: drain, send with \r, wait for response."""
    time.sleep(wait_before)
    # Drain any stale input
    reader.drain(0.5)
    # Send command + newline
    ser.write((cmd + '\r').encode())
    time.sleep(0.3)
    # Drain the echo
    reader.drain(0.3)
    time.sleep(wait_after)
    # Return what came back during wait
    return reader.drain(0.5)

def wait_for(ser, reader, needle, timeout=30):
    """Poll for a string in the serial stream."""
    deadline = time.time() + timeout
    size_start = reader.size()
    while time.time() < deadline:
        time.sleep(1)
        with open(reader.log_path, 'rb') as f:
            data = f.read()
        if needle.encode() in data:
            return True
        if time.time() - deadline > -timeout:
            sys.stdout.write('.')
            sys.stdout.flush()
    return False

# ---- MAIN ----
log("Opening serial port...")
ser = serial.Serial(DEV, BAUD, timeout=1, write_timeout=5)
ser.dtr = False
ser.rts = False
time.sleep(0.5)
if ser.in_waiting:
    ser.read(ser.in_waiting)
log(f"Port open: {DEV}")

reader = SerialReader(ser, LOG)
reader.start()
time.sleep(1)

log("Power cycling...")
os.system("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
os.system("python3 /home/host/smartplug.py on 2>/dev/null")
log("Power on. Waiting 12s for U-Boot...")
time.sleep(12)

size_at_boot = reader.size()
log(f"Log: {size_at_boot} bytes at U-Boot window")

# Intercept autoboot: send multiple \r until "=>" prompt
log("Intercepting autoboot...")
for i in range(5):
    ser.write(b'\r')
    time.sleep(0.5)
    reader.drain(0.3)
    with open(LOG, 'rb') as f:
        data = f.read()
    if b'=>' in data or b'Hit any key' in data:
        log(f"Prompt detected on attempt {i+1}")
        break

time.sleep(1)
reader.drain(1)

# Check current state
with open(LOG, 'rb') as f:
    raw = f.read()
log(f"Log size: {len(raw)} bytes")
lines = raw.decode('utf-8', errors='replace').split('\r')
for l in lines[-10:]:
    l = l.strip()
    if l:
        print(f"  << {l}", flush=True)

# Boot sequence — wait for prompt first
log("Waiting for U-Boot prompt...")
prompt_found = False
for _ in range(20):
    time.sleep(1)
    with open(LOG, 'rb') as f:
        data = f.read()
    if b'=> ' in data or b'=>\r' in data:
        log("U-Boot prompt FOUND")
        prompt_found = True
        break
    reader.drain(0.3)

if not prompt_found:
    log("No U-Boot prompt detected — may need to wait more")
    time.sleep(5)

bootargs = (
    "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 "
    "earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 "
    "console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused "
    "swiotlb=65536 fbcon=map:1 modprobe.blacklist=aic8800_btlpm"
)

log("Setting bootargs...")
# Setenv: split into separate commands to avoid issues
resp = send_cmd(ser, reader, f"setenv bootargs {bootargs}", wait_before=1, wait_after=2)
log(f"bootargs response snippet: {repr(resp[-100:])}")

log("Loading uImage...")
resp = send_cmd(ser, reader, "ext4load mmc 0:1 0x41000000 boot/uImage", wait_before=1, wait_after=8)
log(f"uImage response: {repr(resp[-200:])}")

log("Loading DTB...")
resp = send_cmd(ser, reader, "ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb", wait_before=1, wait_after=3)
log(f"DTB response: {repr(resp[-200:])}")

log("Booting (NO initrd)...")
resp = send_cmd(ser, reader, "bootm 0x41000000 - 0x43000000", wait_before=1, wait_after=5)
log(f"bootm response: {repr(resp[-300:])}")

log("Waiting 90s for kernel to boot...")
wait_for(ser, reader, "login:", timeout=90)

reader.stop()

log("=== FINAL STATE ===")
final_size = reader.size()
log(f"Log: {size_at_boot} -> {final_size} bytes (+{final_size - size_at_boot})")
log("=== Key markers ===")
with open(LOG, 'rb') as f:
    raw = f.read()
text = raw.decode('utf-8', errors='replace')
for marker in ["login:", "Starting kernel", "EXT4-fs: mounted", "aic8800",
               "root@", "orangepi", "Kernel panic", "VFS:", "CPU:"]:
    if marker in text:
        idx = text.index(marker)
        snippet = text[max(0,idx-30):idx+80].replace('\r', '\n').strip()
        log(f"FOUND '{marker}': ...{snippet}...")

log("=== DONE ===")
ser.close()
