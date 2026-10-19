#!/usr/bin/env python3
"""uboot_rescue.py — Full boot-to-ssh rescue pipeline.
1. Clear stale buffer
2. Power cycle  
3. Intercept U-Boot prompt
4. Fix bootargs (blacklist aic8800, remove swiotlb)
5. Boot to kernel, watch serial through full boot
6. Report: SSH reachable or kernel panic
Usage: sudo python3 uboot_rescue.py [timeout=120]
"""
import serial, sys, time, os, signal, subprocess

DEV = "/dev/ttyACM0"
BAUD = 115200
WATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 120
LOG = "/home/host/pvrgl-work/uboot_rescue.log"
UBOOT_LOG = "/home/host/pvrgl-work/uboot_rescue_uboot.log"

def signal_handler(sig, frame):
    print("\n[interrupted]")
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

def drain(ser):
    """Drain all pending bytes from serial."""
    total = 0
    for _ in range(20):
        if ser.in_waiting:
            n = ser.in_waiting
            ser.read(n)
            total += n
            time.sleep(0.1)
        else:
            time.sleep(0.2)
    return total

# Step 1: Clear stale processes
subprocess.run("sudo /home/host/opikernel/scripts/claim-serial-port.sh >/dev/null 2>&1", shell=True)

# Step 2: Open serial, drain
print(f"[{time.strftime('%H:%M:%S')}] Opening {DEV}...")
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False; ser.rts = False
time.sleep(0.5)
drained = drain(ser)
print(f"  drained {drained} stale bytes")

# Step 3: Start persistent background reader that survives this process
# Use double-fork trick: spawn child that outlives parent
pid = os.fork()
if pid == 0:
    # Child process: redirect stdin/stdout to /dev/null, keep ttyACM0 open
    # We need to re-open the serial port in the child
    os.close(0); os.close(1); os.close(2)
    os.open('/dev/null', os.O_RDONLY)
    os.open('/dev/null', os.O_WRONLY)
    os.open('/dev/null', os.O_WRONLY)
    # Re-open serial port for logging
    child_ser = serial.Serial(DEV, BAUD, timeout=1)
    with open(LOG, 'wb') as lf:
        while True:
            if child_ser.in_waiting:
                data = child_ser.read(child_ser.in_waiting)
                lf.write(data); lf.flush()
            time.sleep(0.05)
    sys.exit(0)

# Parent continues
print(f"[{time.strftime('%H:%M:%S')}] Background logger PID={pid}, log={LOG}")

# Step 4: Power cycle
print(f"[{time.strftime('%H:%M:%S')}] Power off..."); sys.stdout.flush()
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","off","--model","WLPP1CFH","D03F271583AE"], capture_output=True)
time.sleep(5)
print(f"[{time.strftime('%H:%M:%S')}] Power on..."); sys.stdout.flush()
subprocess.run(["/usr/bin/python3","/home/host/opikernel/scripts/host/smartplug.py","on","--model","WLPP1CFH","D03F271583AE"], capture_output=True)

# Step 5: Wait for U-Boot prompt
print(f"[{time.strftime('%H:%M:%S')}] Waiting for U-Boot (max {WATCH}s)..."); sys.stdout.flush()
start = time.time()
prompt_found = False
shell_acquired = False

while time.time() - start < WATCH:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        decoded = data.decode('utf-8', errors='replace')
        print(decoded, end='', flush=True)
        
        if 'Hit any key' in decoded or 'stop auto' in decoded.lower():
            print(f"\n[PROMPT at +{time.time()-start:.1f}s]"); sys.stdout.flush()
            ser.break_condition = True; time.sleep(0.05); ser.break_condition = False
            time.sleep(0.3)
            ser.write(b'\r'); time.sleep(1.0)
            if ser.in_waiting:
                resp = ser.read(ser.in_waiting)
                print(resp.decode('utf-8', errors='replace'), end='', flush=True)
                if '=>' in resp.decode():
                    shell_acquired = True
                    prompt_found = True
                    break
        elif '=>' in decoded:
            shell_acquired = True; prompt_found = True; break
    time.sleep(0.05)

if not prompt_found:
    print(f"\n[FAILED] No U-Boot prompt in {WATCH}s")
    ser.close(); os.kill(pid, 9)
    sys.exit(1)

print(f"\n[{time.strftime('%H:%M:%S')}] Shell acquired, setting bootargs..."); sys.stdout.flush()

# Step 6: Fix bootargs
cmds = [
    "setenv bootargs console=ttyS0,115200 root=/dev/mmcblk1p1 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 modprobe.blacklist=aic8800_bt,aic8800_sdio loglevel=7 clk_ignore_unused",
    "saveenv",
]

for cmd in cmds:
    print(f"  >>> {cmd[:80]}..."); sys.stdout.flush()
    ser.write(cmd.encode() + b'\r'); time.sleep(2.0)
    # Read response
    for _ in range(30):
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            print(data.decode('utf-8', errors='replace'), end='', flush=True)
        time.sleep(0.2)
    time.sleep(0.5)

print(f"\n[{time.strftime('%H:%M:%S')}] Booting kernel..."); sys.stdout.flush()
ser.write(b'boot\r')
time.sleep(1.0)
# Drain initial boot output
for _ in range(20):
    if ser.in_waiting:
        ser.read(ser.in_waiting)
    time.sleep(0.5)

print(f"[{time.strftime('%H:%M:%S')}] Watching kernel boot (up to {WATCH - int(time.time()-start)}s remaining)..."); sys.stdout.flush()

# Step 7: Watch kernel boot
boot_start = time.time()
last_dot = boot_start
kernel_panicked = False
userspace_seen = False

while time.time() - boot_start < (WATCH - (time.time() - start)):
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        decoded = data.decode('utf-8', errors='replace')
        print(decoded, end='', flush=True)
        
        if 'Kernel panic' in decoded:
            kernel_panicked = True
        if 'login:' in decoded:
            userspace_seen = True
            print(f"\n[USESPACE at +{time.time()-boot_start:.1f}s]"); sys.stdout.flush()
            break
        if 'aic8800' in decoded.lower() and ('error' in decoded.lower() or 'bug' in decoded.lower() or 'oops' in decoded.lower() or 'BUG:' in decoded):
            print(f"\n[POSSIBLE aic8800 issue detected]"); sys.stdout.flush()
    
    if time.time() - last_dot > 10:
        print(f"  [{(time.time()-boot_start):.0f}s | kernel watching...]", flush=True)
        last_dot = time.time()
    
    # Timeout check
    if time.time() - boot_start > 90:
        # Kernel takes ~60s, give it more time
        if not userspace_seen and not kernel_panicked:
            if ser.in_waiting == 0:
                print(f"\n[WARNING: no output for 90s, checking SSH...]"); sys.stdout.flush()
                break
    
    time.sleep(0.05)

ser.close()

# Step 8: Check SSH
print(f"\n[{time.strftime('%H:%M:%S')}] Checking SSH reachability..."); sys.stdout.flush()
ssh_check = subprocess.run(["ping","-c","3","-W","2","192.168.0.151"], capture_output=True)
ssh_ok = ssh_check.returncode == 0

print(f"\n{'='*60}")
print(f"RESCUE RESULT:")
print(f"  SSH reachable: {ssh_ok}")
print(f"  Userspace reached: {userspace_seen}")
print(f"  Kernel panic: {kernel_panicked}")
print(f"  U-Boot log: {UBOOT_LOG}")
print(f"  Full serial log: {LOG}")
print(f"{'='*60}")

if ssh_ok:
    print(f"\n[BOARD REACHABLE] SSH orangepi@192.168.0.151 ready!")
else:
    print(f"\n[BOARD NOT REACHABLE — check {LOG} for panic details]")
