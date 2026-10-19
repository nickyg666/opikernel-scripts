#!/usr/bin/env python3
"""Minimal mainline boot — no kill loop, no os.popen, pure fork+setsid."""
import time, serial, sys, os, socket, signal

TTY = "/dev/ttyACM0"
BAUD = 115200
LOG = "/home/host/opikernel/pvrgl-work/boot_quick.log"
BOARD = "192.168.0.151"
KERNEL = "/boot/mainline/Image"
INITRD = "/boot/mainline/initrd6.19.gz"
DTB = "/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.de-noiommu"
A = "root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

def log(m):
    ts = time.strftime("%H:%M:%S")
    open(LOG,"a").write(f"[{ts}] {m}\n")
    print(f"[{ts}] {m}", flush=True)

# Fork background reader — survives parent death
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
    log("FAIL no port"); sys.exit(1)

# Serial
try: s = serial.Serial(TTY, BAUD, timeout=1); s.reset_input_buffer()
except Exception as e:
    log(f"Serial fail: {e}"); sys.exit(1)

# BREAK spam
log("Break spam")
for _ in range(20): s.write(b'\r'); s.flush(); time.sleep(.25)
s.break_condition=True; time.sleep(.05); s.break_condition=False
time.sleep(1)

# Drain stale
while s.in_waiting: s.read(s.in_waiting)
time.sleep(1)

# Wait for U-Boot
dl=time.time()+20
while time.time()<dl:
    if s.in_waiting:
        d=s.read(s.in_waiting); t=d.decode('latin-1','replace')
        for l in t.split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
        if '=> ' in t or 'Hit any' in t:
            log("U-Boot OK"); break
    time.sleep(.05)
else:
    log("No prompt — blind"); s.write(b'\r'); s.flush(); time.sleep(1)

# Boot commands
cmds=[
    (f"setenv bootargs {A}", 1),
    (f"ext4load mmc 0:1 0x41000000 {KERNEL}", 45),
    (f"ext4load mmc 0:1 0x43300000 {INITRD}", 60),
    (f"ext4load mmc 0:1 0x43000000 {DTB}", 5),
    ("fdt addr 0x43000000", 1),
    ("fdt resize 65536", 1),
    ("booti 0x41000000 - 0x43000000", 5),
]
for cmd,wait in cmds:
    log(f">>> {cmd[:80]}")
    s.write((cmd+'\r').encode()); s.flush()
    time.sleep(wait)
    buf=b''
    dl2=time.time()+wait+2
    while time.time()<dl2:
        if s.in_waiting: buf+=s.read(s.in_waiting)
        time.sleep(.05)
    if buf:
        for l in buf.decode('latin-1','replace').split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
s.close()
log("Booting — poll SSH 300s")
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
