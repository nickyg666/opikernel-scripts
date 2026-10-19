#!/usr/bin/env python3
"""uboot_intercept.py — Catch U-Boot boot prompt, send break, get to shell.
Usage: sudo python3 uboot_intercept.py [timeout_seconds]
"""
import serial, sys, time, os, signal

DEV = "/dev/ttyACM0"
BAUD = 115200
TIMEOUT = int(sys.argv[1]) if len(sys.argv) > 1 else 90
LOG = "/home/host/pvrgl-work/uboot_intercept.log"

def signal_handler(sig, frame):
    print(f"\n[interrupted, log at {LOG}]")
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

# Drain stale data
ser = serial.Serial(DEV, BAUD, timeout=1)
ser.dtr = False
ser.rts = False
time.sleep(0.5)
if ser.in_waiting:
    ser.read(ser.in_waiting)

# Start logging to file
log_fd = open(LOG, "wb")
log_start = os.fstat(log_fd.fileno()).st_size

print(f"[{time.strftime('%H:%M:%S')}] watching {DEV} @ {BAUD} for {TIMEOUT}s...")

# Wait loop
start = time.time()
last_dot = start
found_prompt = False
lines_since_dot = 0

while time.time() - start < TIMEOUT:
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
        log_fd.write(data)
        log_fd.flush()
        decoded = data.decode('utf-8', errors='replace')
        print(decoded, end='', flush=True)
        lines_since_dot += decoded.count('\n')
        
        # Detect "Hit any key" prompt
        if 'Hit any key' in decoded or 'stop auto' in decoded.lower():
            found_prompt = True
            print(f"\n[PROMPT DETECTED at {time.time()-start:.1f}s] sending break...")
            # Send break signal
            ser.break_condition = True
            time.sleep(0.05)
            ser.break_condition = False
            time.sleep(0.1)
            # Send newline to trigger prompt
            ser.write(b'\r')
            time.sleep(0.5)
            # Drain response
            if ser.in_waiting:
                resp = ser.read(ser.in_waiting)
                log_fd.write(resp)
                log_fd.flush()
                print(resp.decode('utf-8', errors='replace'), end='', flush=True)
            break
        
        # Status dot every 5s
        if time.time() - last_dot > 5:
            elapsed = int(time.time() - start)
            print(f"  [{elapsed}s elapsed, no prompt yet]", flush=True)
            last_dot = time.time()
    
    time.sleep(0.05)

log_fd.close()
ser.close()

# Check result
with open(LOG, "rb") as f:
    content = f.read().decode('utf-8', errors='replace')

if found_prompt:
    print(f"\n[SUCCESS] Prompt intercepted, log: {LOG}")
    # Check if we got a shell prompt
    if '=>' in content or '#' in content:
        print("[SHELL READY] U-Boot shell available")
    else:
        print("[PROMPT FOUND but no shell yet — may need more time]")
else:
    print(f"\n[FAILED] No prompt found in {TIMEOUT}s")
    print(f"  Last 2000 chars of log:")
    print(content[-2000:])
