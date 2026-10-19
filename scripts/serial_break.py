#!/usr/bin/env python3
import serial, time, sys

port = '/dev/ttyACM0'
try:
    s = serial.Serial(port, 115200, timeout=1)
    time.sleep(1)
    s.reset_input_buffer()
    s.reset_output_buffer()
    
    # Try to break into U-Boot with Ctrl+C during boot
    # Send Ctrl+C multiple times
    for i in range(10):
        s.write(b'\x03')  # Ctrl+C
        time.sleep(0.2)
    
    time.sleep(2)
    
    # Now try to read any response
    raw = s.read(8192)
    text = raw.decode('utf-8', errors='replace')
    print("=== RESPONSE (len=%d) ===" % len(raw))
    if text.strip():
        print(text[:3000])
    else:
        print("[empty response]")
        print("hex dump:", raw[:100].hex())
    print("=== END ===")
    s.close()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
