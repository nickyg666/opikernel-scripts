#!/usr/bin/env python3
"""Mainline boot — correct initrd (33MB), correct DTB, no distro_bootcmd interference."""
import time, serial, sys, os, socket

TTY = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/opikernel/pvrgl-work/boot_final.log"
BOARD = "192.168.0.151"
KERNEL = "/boot/mainline/Image"
INITRD = "/boot/mainline/initrd6.19.gz"
DTB    = "/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.de-noiommu"
A = "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

def log(m):
    ts = time.strftime("%H:%M:%S")
    open(LOG,"a").write(f"[{ts}] {m}\n")
    print(f"[{ts}] {m}", flush=True)

# Fork reader (survives parent death)
pid = os.fork()
if pid == 0:
    os.setsid()
    open(LOG,"w").write("")
    fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
    f = open(LOG,"ab",0)
    while 1:
        r = os.read(fd,4096)
        if r: f.write(r); f.flush()
        else: time.sleep(.1)
    sys.exit(0)
log(f"Reader PID={pid}")
time.sleep(1)

# Power cycle
log("Power off")
os.system("/home/host/smartplug.py off 2>/dev/null"); time.sleep(8)
log("Power on")
os.system("/home/host/smartplug.py on 2>/dev/null")

# Wait for port
log("Wait port")
for i in range(30):
    if os.path.exists(TTY):
        st=os.stat(TTY)
        if (st.st_mode & 0o170000)==0o020000:
            log(f"Port T+{i}s"); time.sleep(3); break
    time.sleep(1)
else:
    log("FAIL: no port"); sys.exit(1)

# Serial
try: s = serial.Serial(TTY, BAUD, timeout=1); s.reset_input_buffer()
except Exception as e:
    log(f"Serial fail: {e}"); sys.exit(1)

# BREAK spam to catch distro_bootcmd countdown
log("Break spam")
for _ in range(20): s.write(b'\r'); s.flush(); time.sleep(.25)
s.break_condition=True; time.sleep(.05); s.break_condition=False
time.sleep(1)
while s.in_waiting: s.read(s.in_waiting)

# Wait for U-Boot prompt
dl=time.time()+20
while time.time()<dl:
    if s.in_waiting:
        d=s.read(s.in_waiting); t=d.decode('latin-1','replace')
        for l in t.split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
        if '=> ' in t or '# ' in t:
            log("U-Boot OK"); break
    time.sleep(.05)
else:
    log("Blind proceed"); s.write(b'\r'); s.flush(); time.sleep(1)
    while s.in_waiting: s.read(s.in_waiting)

# === BOOT SEQUENCE ===
# Step 1: Disable distro_bootcmd FIRST — prevents auto-boot between our commands
log(">>> setenv bootcmd ''")
s.write(b"setenv bootcmd ''\r"); s.flush(); time.sleep(1)
while s.in_waiting: s.read(s.in_waiting)

# Step 2: Load kernel
log(f">>> ext4load {KERNEL}")
s.write(f"ext4load mmc 0:1 0x41000000 {KERNEL}\r".encode()); s.flush()
time.sleep(5)
buf=b''
dl=time.time()+60
while time.time()<dl:
    if s.in_waiting: buf+=s.read(s.in_waiting)
    time.sleep(.05)
t=buf.decode('latin-1','replace')
for l in t.split('\r\n'):
    if l.strip(): print(f"  {l}", flush=True)
# Check for bytes-read confirmation
if b'bytes read' in buf or b'Loading' in buf:
    log("Kernel loaded OK")
else:
    log("WARNING: kernel load unclear")

# Step 3: Load initrd
log(f">>> ext4load {INITRD}")
s.write(f"ext4load mmc 0:1 0x43300000 {INITRD}\r".encode()); s.flush()
time.sleep(5)
buf=b''
dl=time.time()+90
while time.time()<dl:
    if s.in_waiting: buf+=s.read(s.in_waiting)
    time.sleep(.05)
t=buf.decode('latin-1','replace')
for l in t.split('\r\n'):
    if l.strip(): print(f"  {l}", flush=True)
if b'bytes read' in buf or b'Loading' in buf:
    log("Initrd loaded OK")
else:
    log("WARNING: initrd load unclear")

# Step 4: Load DTB
log(f">>> ext4load {DTB}")
s.write(f"ext4load mmc 0:1 0x43000000 {DTB}\r".encode()); s.flush()
time.sleep(3)
buf=b''
dl=time.time()+10
while time.time()<dl:
    if s.in_waiting: buf+=s.read(s.in_waiting)
    time.sleep(.05)
t=buf.decode('latin-1','replace')
for l in t.split('\r\n'):
    if l.strip(): print(f"  {l}", flush=True)

# Step 5: Set bootargs AND fdt commands (after all loads)
log(">>> fdt addr + resize")
s.write(b"fdt addr 0x43000000\r"); s.flush(); time.sleep(1)
while s.in_waiting: s.read(s.in_waiting)
s.write(b"fdt resize 65536\r"); s.flush(); time.sleep(1)
while s.in_waiting: s.read(s.in_waiting)

log(f">>> setenv bootargs {A[:60]}...")
s.write((f"setenv bootargs {A}\r").encode()); s.flush(); time.sleep(2)
while s.in_waiting: s.read(s.in_waiting)

# Step 6: BOOT
log(">>> booti 0x41000000 - 0x43000000")
s.write(b"booti 0x41000000 - 0x43000000\r"); s.flush(); time.sleep(3)
while s.in_waiting: s.read(s.in_waiting)
s.close()

log("Booting — poll SSH for 300s...")
t0=time.time()
for i in range(60):
    time.sleep(5)
    try:
        sk=socket.socket(); sk.settimeout(2)
        if sk.connect_ex((BOARD,22))==0:
            sk.close()
            log(f"SSH UP T+{int(time.time()-t0)}s"); sys.exit(0)
    except: pass
    if i%6==0: log(f"  ~{int(time.time()-t0)}s...")
log(f"FAIL T+{int(time.time()-t0)}s")
