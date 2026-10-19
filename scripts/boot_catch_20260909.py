#!/usr/bin/env python3
"""Catch U-Boot autoboot via continuous CR spam during the full boot window,
then boot the board with the correct DTB. Logs everything to a file."""
import serial, time, sys

LOG = '/home/host/opikernel/logs/boot-catch-20260909.log'
port = '/dev/ttyACM0'
baud = 1500000

log = open(LOG, 'a', buffering=1)
try:
    ser = serial.Serial(port, baud, timeout=0.05)
    ser.reset_input_buffer()

    log.write(f"\n\n=== boot attempt {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    start = time.time()
    buffer = b""
    at_prompt = False

    # Continuous CR spam the whole time (cheap; U-Boot ignores CRs at prompt)
    while time.time() - start < 100:
        try:
            ser.write(b'\r')
            time.sleep(0.004)
            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                buffer += data
                log.write(data.decode('utf-8', errors='replace'))
                if b'=>' in data and not at_prompt:
                    at_prompt = True
                    log.write("\n--- entering U-Boot prompt ---\n")
                    break
        except Exception as e:
            log.write(f"\n[serial error: {e}]\n")
            time.sleep(1)

    if at_prompt:
        for cmd in [
            'ext4load mmc 0:1 0x43000000 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb',
            'fdt addr 0x43000000',
            'fdt resize 65536',
            'bootm 0x41000000 - 0x43000000',
        ]:
            ser.write((cmd + '\r').encode())
            time.sleep(2)
            while ser.in_waiting:
                data = ser.read(ser.in_waiting)
                buffer += data
                log.write(data.decode('utf-8', errors='replace'))

        # Capture kernel boot for 40s
        t2 = time.time()
        while time.time() - t2 < 40:
            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                buffer += data
                log.write(data.decode('utf-8', errors='replace'))
            time.sleep(0.05)
    log.write("\n=== attempt end ===\n")
    log.close()
    ser.close()
    print("done: at_prompt=%s" % at_prompt)
except Exception as e:
    try:
        log.write(f"\n[fatal: {e}]\n")
        log.close()
    except Exception:
        pass
    print(f"error: {e}")
