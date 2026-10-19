#!/usr/bin/env python3
"""Sequential mainline boot. Fork reader (exit immediately), then power+boot sequence."""
import time, os, sys, select, fcntl

TTY="/dev/ttyACM0"; LOG="/home/host/opikernel/pvrgl-work/boot_seq.log"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.de-noiommu"
A="root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"
TIOCSBRK=0x5427; TIOCCBRK=0x5428

def log(m):
    print(m, flush=True)
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

def drain(fd, t=0.5):
    time.sleep(t)
    buf=b''; dl=time.time()+t*3
    while time.time()<dl:
        r,_,_=select.select([fd],[],[],0.1)
        if r: buf+=os.read(fd,4096)
        else: break
    return buf

def cmd(fd, c, wait=2):
    os.write(fd,(c+"\r\n").encode())
    time.sleep(0.3)
    buf=drain(fd,wait)
    for l in buf.decode('latin-1','replace').split('\r\n'):
        if l.strip(): print(f"  {l}", flush=True)
    return buf

def open_tty():
    """Open ttyACM0 with retry (device may vanish during USB reset)."""
    for i in range(10):
        try:
            fd=os.open(TTY, os.O_RDWR)
            return fd
        except OSError as e:
            if e.errno == 6:  # ENXIO - device temporarily gone
                time.sleep(1)
                continue
            raise
    raise RuntimeError(f"Could not open {TTY} after 10 retries")

# Step 1: Fork reader (parent exits immediately)
pid = os.fork()
if pid == 0:
    for attempt in range(30):
        try:
            fd=os.open(TTY, os.O_RDWR)
            f=open(LOG,"wb",0)
            while True:
                r,_,_=select.select([fd],[],[],1)
                if r:
                    d=os.read(fd,4096)
                    if d: f.write(d)
                else:
                    time.sleep(0.1)
        except OSError:
            time.sleep(1)
            continue
    os._exit(0)

log(f"Reader PID={pid}")
log("=== SEQUENTIAL BOOT ===")

# Step 2: Power cycle
log("Power off")
os.system("/home/host/smartplug.py off"); time.sleep(9)
log("Power on")
os.system("/home/host/smartplug.py on")

# Step 3: Wait for port with retry
log("Wait for port")
port_ready=False
for i in range(30):
    if os.path.exists(TTY):
        try:
            st=os.stat(TTY)
            if (st.st_mode&0o170000)==0o020000:
                time.sleep(3)  # settle after USB rebind
                log(f"Port ready T+{i}s"); port_ready=True; break
        except OSError:
            pass
    time.sleep(1)
if not port_ready:
    log("FAIL: no port"); sys.exit(1)

# Step 4: Open serial
fd=open_tty()
log("Port open")

# Step 5: CR spam + BREAK
for _ in range(15): os.write(fd,b'\r'); time.sleep(.25)
fcntl.ioctl(fd,TIOCSBRK); time.sleep(.05); fcntl.ioctl(fd,TIOCCBRK)
time.sleep(1); drain(fd,1)

# Step 6: Wait U-Boot
dl=time.time()+18
in_shell=False
while time.time()<dl:
    r,_,_=select.select([fd],[],[],0.2)
    if r:
        d=os.read(fd,4096); t=d.decode('latin-1','replace')
        for l in t.split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
        if '=> ' in t or '# ' in t:
            log("U-Boot OK"); in_shell=True; break
else:
    log("Blind proceed"); os.write(fd,b'\r\n'); drain(fd,1)

# Step 7: Boot sequence
log("setenv bootcmd ''")
drain(fd,1)
os.write(fd,b"setenv bootcmd ''\r\n"); drain(fd,2)

log(f"load kernel {KERNEL}")
os.write(fd,f"ext4load mmc 0:1 0x41000000 {KERNEL}\r\n".encode())
buf=drain(fd,20)
for l in buf.decode('latin-1','replace').split('\r\n'):
    if l.strip(): print(f"  {l}", flush=True)
if b'bytes read' in buf: log("Kernel OK")

log(f"load initrd {INITRD}")
os.write(fd,f"ext4load mmc 0:1 0x43300000 {INITRD}\r\n".encode())
buf=drain(fd,40)
for l in buf.decode('latin-1','replace').split('\r\n'):
    if l.strip(): print(f"  {l}", flush=True)
if b'bytes read' in buf: log("Initrd OK")

log(f"load dtb {DTB}")
os.write(fd,f"ext4load mmc 0:1 0x43000000 {DTB}\r\n".encode())
buf=drain(fd,10)
for l in buf.decode('latin-1','replace').split('\r\n'):
    if l.strip(): print(f"  {l}", flush=True)
if b'bytes read' in buf: log("DTB OK")

log("fdt + bootargs")
os.write(fd,b"fdt addr 0x43000000\r\n"); drain(fd,1)
os.write(fd,b"fdt resize 65536\r\n"); drain(fd,1)
os.write(fd,f"setenv bootargs {A}\r\n".encode()); drain(fd,2)

log("BOOTI!")
os.write(fd,b"booti 0x41000000 - 0x43000000\r\n")
drain(fd,3)
os.close(fd)
log("BOOTING — done")
