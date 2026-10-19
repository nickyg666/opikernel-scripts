#!/usr/bin/env python3
"""Clean boot: pyserial daemon with auto-reconnect + manual U-Boot intercept + vendor boot."""
import os, sys, time, subprocess, serial

DEV = "/dev/serial/by-id/usb-Raspberry_Pi_Pico_5054316540DA319C-if00"
LOG = "/home/host/pvrgl-work/boot_clean.log"
PIDFILE = "/tmp/ser_clean.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

# Kill competing processes
log("Killing competing readers...")
sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
time.sleep(1)

# Fork daemon reader with auto-reconnect
log("Starting daemon reader...")
sh(f"rm -f {LOG}")
pid = os.fork()
if pid == 0:
    os.setsid()
    os.close(0); os.close(1); os.close(2)
    while True:
        try:
            ser = serial.Serial(DEV, 115200, timeout=1.0)
            log(f"[DAEMON] Connected on {DEV}")
            with open(LOG, 'ab') as out:
                while True:
                    d = ser.read(4096)
                    if d:
                        out.write(d); out.flush()
                    else:
                        time.sleep(0.1)
            ser.close()
        except serial.SerialException as e:
            log(f"[DAEMON] Serial error: {e}, reconnecting in 1s...")
            time.sleep(1.0)
        except Exception as e:
            log(f"[DAEMON] Unexpected: {e}")
            break
    sys.exit(0)
else:
    with open(PIDFILE, 'w') as f:
        f.write(str(pid))
    time.sleep(2)
    log(f"Daemon PID={pid}")

# Power cycle
log("Power OFF...")
sh("python3 /home/host/smartplug.py off 2>/dev/null")
time.sleep(5)
log("Power ON...")
sh("python3 /home/host/smartplug.py on 2>/dev/null")

# Wait for U-Boot to appear
log("Waiting 13s for U-Boot...")
time.sleep(13)

# Send BREAK spam during countdown
log("Sending BREAK spam...")
for _ in range(20):
    try:
        ser = serial.Serial(DEV, 115200, timeout=0.1)
        ser.write(b'\r')
        ser.close()
    except:
        pass
    time.sleep(0.25)
time.sleep(3)

# Wait for U-Boot prompt
prompt_found = False
for _ in range(15):
    time.sleep(1)
    try:
        with open(LOG, 'rb') as f:
            text = f.read().decode('latin-1', errors='replace')
        if '=>' in text:
            prompt_found = True
            log("U-Boot prompt found!")
            break
    except:
        pass

if not prompt_found:
    log("No U-Boot prompt. Last log bytes:")
    try:
        with open(LOG, 'rb') as f:
            data = f.read()
        log(repr(data[-500:]))
    except:
        pass
    sys.exit(1)

# Boot sequence
log("Sending vendor boot commands...")
ser = serial.Serial(DEV, 115200, timeout=0.5)
try:
    def send(cmd, delay=2):
        ser.write((cmd + '\r').encode())
        ser.flush()
        time.sleep(delay)
        log(f"  >> {cmd[:60]}")

    send("setenv distro_bootcmd ''")
    time.sleep(1)
    send("setenv bootcmd \"ext4load mmc 0:1 0x41000000 boot/uImage && ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb && bootm 0x41000000 - 0x43000000\"", delay=3)
    send("run bootcmd", delay=5)
finally:
    ser.close()

log("Boot dispatched. Monitoring for 120s...")
sz_start = os.path.getsize(LOG)
for i in range(12):
    time.sleep(10)
    sz = os.path.getsize(LOG)
    log(f"  T+{(i+1)*10}s: {sz} bytes (+{sz-sz_start})")
    r = subprocess.run(
        ["sshpass", "-p", "orangepi", "ssh", "-o", "StrictHostKeyChecking=accept-new",
         "-o", "ConnectTimeout=3", "orangepi@192.168.0.151", "uptime"],
        capture_output=True, text=True, timeout=8
    )
    if r.returncode == 0:
        log(f"BOARD ONLINE: {r.stdout.strip()}")
        break
else:
    log("WARNING: Board may not be online yet")

log("Done.")
