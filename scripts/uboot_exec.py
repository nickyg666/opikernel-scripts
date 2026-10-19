#!/usr/bin/env python3
"""uboot_exec.py — Execute commands in U-Boot shell over serial.
Usage: sudo python3 uboot_exec.py [cmd [cmd...]]
       With no args: interactive shell
"""
import serial, sys, time, signal

DEV = "/dev/ttyACM0"
BAUD = 115200

def signal_handler(sig, frame):
    print("\n[interrupted]")
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

ser = serial.Serial(DEV, BAUD, timeout=3)
ser.dtr = False
ser.rts = False

def send(cmd, wait=1.0):
    """Send command and return response."""
    ser.write(cmd.encode() + b'\r')
    time.sleep(0.1)
    out = b''
    for _ in range(int(wait * 10)):
        if ser.in_waiting:
            out += ser.read(ser.in_waiting)
        time.sleep(0.1)
    return out.decode('utf-8', errors='replace')

def get_lines(resp, prompt='=>'):
    """Extract lines from response, removing prompt-echo artifacts."""
    lines = []
    for line in resp.split('\r\n'):
        line = line.strip()
        if line and line != prompt and not line.startswith(cmd_echo):
            lines.append(line)
    return lines

# Drain any pending
if ser.in_waiting:
    ser.read(ser.in_waiting)

if len(sys.argv) < 2:
    print("Interactive U-Boot shell. Type 'exit' to quit.")
    while True:
        cmd = input("uboot> ")
        if cmd.lower() in ('exit', 'quit', 'q'):
            break
        if not cmd.strip():
            continue
        resp = send(cmd)
        print(resp, end='')
    ser.close()
    sys.exit(0)

# Batch commands
cmd_echo = sys.argv[1]
for cmd in sys.argv[1:]:
    print(f">>> {cmd}")
    resp = send(cmd)
    # Print non-prompt lines
    for line in resp.split('\r'):
        line = line.strip()
        if line and '=>' not in line and line != cmd:
            print(f"    {line}")
ser.close()
