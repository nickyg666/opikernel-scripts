#!/usr/bin/env python3
"""Boot script using setsid to detach from terminal — no daemon fork.
All serial reads/writes in one foreground process, managed by setsid."""
import os, sys, time, subprocess, serial

DEV = "/dev/serial/by-id/usb-Raspberry_Pi_Pico_5054316540DA319C-if00"
LOG = "/home/host/pvrgl-work/boot_setsid.log"
PIDFILE = "/tmp/ser_setsid.pid"

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    # Write to both stdout (captured by shell wrapper) and log file
    print(line, flush=True)
    with open(LOG + ".txt", 'a') as f:
        f.write(line + '\n')

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

def send(ser, cmd, delay=2):
    ser.write((cmd + '\r').encode())
    ser.flush()
    time.sleep(delay)
    log(f">> {cmd[:80]}")

def main():
    # Note: setsid() is called by the shell wrapper (setsid python3 ...)
    # Do NOT call it here — Python lacks CAP_SYS_TTY in this context
    # The shell wrapper has already redirected its stdout/stderr to the log file.
    # We write to LOG.txt directly to be safe.

    log("=== Boot setsid: vendor kernel ===")

    # Kill competing readers
    sh("pkill -f 'cat.*ttyACM' 2>/dev/null")
    time.sleep(1)

    # Open serial port for entire session
    log(f"Opening {DEV}...")
    ser = serial.Serial(DEV, 115200, timeout=1.0)
    log("Serial connected")

    # Power cycle
    log("Power OFF...")
    sh("python3 /home/host/smartplug.py off 2>/dev/null")
    time.sleep(5)
    log("Power ON...")
    sh("python3 /home/host/smartplug.py on 2>/dev/null")

    # Wait for U-Boot
    log("Waiting 13s...")
    time.sleep(13)

    # Spam BREAK
    log("BREAK spam...")
    for _ in range(20):
        ser.write(b'\r')
        ser.flush()
        time.sleep(0.25)
    time.sleep(3)

    # Drain serial buffer
    ser.timeout = 0.1
    while ser.read(4096):
        pass
    ser.timeout = 1.0

    # Wait for U-Boot prompt
    log("Waiting for '=>'...")
    for _ in range(20):
        time.sleep(1)
        buf = ser.read(4096)
        if buf:
            with open(LOG, 'ab') as f:
                f.write(buf)
        with open(LOG, 'rb') as f:
            text = f.read().decode('latin-1', errors='replace')
        if '=>' in text:
            log("U-Boot prompt found!")
            break
    else:
        log("No U-Boot prompt!")
        sys.exit(1)

    # Boot sequence
    log("Sending vendor boot...")
    send(ser, "setenv distro_bootcmd ''")
    time.sleep(1)
    send(ser, "setenv bootcmd \"ext4load mmc 0:1 0x41000000 boot/uImage && ext4load mmc 0:1 0x43000000 boot/dtb-6.6.98-sun60iw2/allwinner/sun60i-a733-orangepi-zero3w.dtb && bootm 0x41000000 - 0x43000000\"", delay=3)
    send(ser, "run bootcmd", delay=5)

    log("Monitoring kernel boot (120s)...")
    sz_start = os.path.getsize(LOG)
    for i in range(12):
        time.sleep(10)
        # Read serial data
        buf = ser.read(4096)
        if buf:
            with open(LOG, 'ab') as f:
                f.write(buf)
        sz = os.path.getsize(LOG)
        log(f"  T+{(i+1)*10}s: {sz} bytes")
        # Check SSH
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

    ser.close()
    log("Done.")

if __name__ == '__main__':
    main()
