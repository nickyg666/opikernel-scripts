#!/usr/bin/env python3
"""Single foreground mainline boot. All ops within 30s foreground blocks."""
import time, serial, sys, os, socket

TTY="/dev/ttyACM0"; BAUD=115200
LOG="/home/host/opikernel/pvrgl-work/boot_fg.log"
BOARD="192.168.0.151"
KERNEL="/boot/mainline/Image"
INITRD="/boot/mainline/initrd6.19.gz"
DTB="/boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.de-noiommu"
A="root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm,aic8800_sdio console=ttyS0,115200 quiet"

def log(m):
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def drain(s):
    while s.in_waiting: s.read(s.in_waiting)

def send(s, cmd, wait=2):
    s.write((cmd+"\r").encode()); s.flush()
    time.sleep(wait)
    buf=b''
    dl=time.time()+wait+1
    while time.time()<dl:
        if s.in_waiting: buf+=s.read(s.in_waiting)
        time.sleep(.05)
    t=buf.decode('latin-1','replace')
    for l in t.split('\r\n'):
        if l.strip(): print(f"  {l}", flush=True)
    return buf

# 1. Kill stale, fork reader
for pid_str in os.popen("ps aux | grep 'boot_\\|serial_\\|ttyACM' | grep -v grep | awk '{print $2}'").read().split():
    try: os.kill(int(pid_str), 9)
    except: pass
time.sleep(1)
log("=== BOOT_FG ===")

pid=os.fork()
if pid==0:
    os.setsid()
    open(LOG,"w").write("")
    fd=os.open(TTY, os.O_RDWR|os.O_NOCTTY)
    f=open(LOG,"ab",0)
    while 1:
        r=os.read(fd,4096)
        if r: f.write(r); f.flush()
        else: time.sleep(.1)
    sys.exit(0)
log(f"Reader PID={pid}")
time.sleep(1)

# 2. Power cycle (8s block)
log("Power off")
os.system("/home/host/smartplug.py off"); time.sleep(8)
log("Power on")
os.system("/home/host/smartplug.py on")

# 3. Wait port (15s block)
for i in range(15):
    if os.path.exists(TTY) and (os.stat(TTY).st_mode&0o170000)==0o020000:
        log(f"Port T+{i}s, settle 2s"); time.sleep(2); break
    time.sleep(1)
else:
    log("FAIL no port"); sys.exit(1)

# 4. Open serial (fast)
s=serial.Serial(TTY,BAUD,timeout=1)
s.reset_input_buffer()
drain(s)
log("Port open")

# 5. BREAK spam (5s block)
log("Break spam")
for _ in range(10): s.write(b'\r'); s.flush(); time.sleep(.25)
s.break_condition=True; time.sleep(.05); s.break_condition=False
time.sleep(1); drain(s)

# 6. Wait U-Boot (15s block)
dl=time.time()+15
while time.time()<dl:
    if s.in_waiting:
        d=s.read(s.in_waiting); t=d.decode('latin-1','replace')
        for l in t.split('\r\n'):
            if l.strip(): print(f"  {l}", flush=True)
        if '=> ' in t or '# ' in t: log("U-Boot OK"); break
    time.sleep(.05)
else:
    log("Blind proceed"); s.write(b'\r'); s.flush(); time.sleep(1); drain(s)

# 7. Boot sequence — setenv bootcmd '' FIRST
log("Disabling bootcmd...")
send(s,"setenv bootcmd ''",1)
drain(s)

# 8. Load kernel (~30s block, 26MB @ ~23MB/s = ~2s but add margin)
log("Load kernel...")
send(s,f"ext4load mmc 0:1 0x41000000 {KERNEL}",45)

# 9. Load initrd (~90s block, 33MB)
log("Load initrd...")
send(s,f"ext4load mmc 0:1 0x43300000 {INITRD}",90)

# 10. Load DTB
log("Load DTB...")
send(s,f"ext4load mmc 0:1 0x43000000 {DTB}",10)

# 11. fdt + bootargs
log("fdt + bootargs...")
send(s,"fdt addr 0x43000000",1)
send(s,"fdt resize 65536",1)
send(s,f"setenv bootargs {A}",2)
drain(s)

# 12. BOOT
log("BOOTI!")
send(s,"booti 0x41000000 - 0x43000000",5)
drain(s)
s.close()
log("Monitoring SSH...")

# 13. Poll SSH in 10s blocks (max 60 blocks = 600s)
t0=time.time()
for i in range(60):
    time.sleep(10)
    try:
        sk=socket.socket(); sk.settimeout(3)
        if sk.connect_ex((BOARD,22))==0:
            sk.close()
            log(f"SSH UP T+{int(time.time()-t0)}s!"); sys.exit(0)
    except: pass
    log(f"  ~{int(time.time()-t0)}s...")
log(f"FAIL T+{int(time.time()-t0)}s")
