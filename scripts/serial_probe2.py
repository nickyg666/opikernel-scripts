#!/usr/bin/env python3
import serial, time, sys

port = '/dev/ttyACM0'
try:
    s = serial.Serial(port, 115200, timeout=2)
    time.sleep(1)
    s.reset_input_buffer()
    s.reset_output_buffer()
    
    # Send commands that would work at U-Boot prompt
    cmds = [b'help\n', b'version\n', 'printenv\n'.encode(), b'\n', b'version\n']
    for cmd in cmds:
        s.write(cmd)
        time.sleep(1.5)
        try:
            raw = s.read(4096)
            if raw:
                text = raw.decode('utf-8', errors='replace')
                print(f"=== RESPONSE to {cmd} ===")
                print(text[:2000])
                print("=== END ===")
        except:
            pass
    
    s.close()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
