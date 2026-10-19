#!/usr/bin/env python3
import serial, time, sys

port = '/dev/ttyACM0'
try:
    s = serial.Serial(port, 115200, timeout=5)
    time.sleep(1)
    s.reset_input_buffer()
    s.reset_output_buffer()
    # Send multiple newlines to trigger any prompt
    for i in range(5):
        s.write(b'\n')
        time.sleep(0.3)
    time.sleep(2)
    raw = s.read(8192)
    text = raw.decode('utf-8', errors='replace')
    print("=== SERIAL OUTPUT (len=%d) ===" % len(raw))
    if text.strip():
        print(text)
    else:
        print("[no text output]")
        # Show raw hex
        print("hex:", raw[:200].hex())
    print("=== END ===")
    s.close()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
