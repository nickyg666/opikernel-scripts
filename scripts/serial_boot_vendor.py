#!/usr/bin/env python3
"""Serial boot: vendor kernel (proven working) + SSH verify.
Key fixes:
  - NO setenv bootargs (causes FDT_ERR_NOSPACE at 0x43000000)
  - Vendor uImage has built-in bootargs + initrd
  - ttyACM1 reopen needs 5s settle time after power cycle
  - Watch for "Hit any key" before sending commands
"""
import os, time, subprocess, select

TTY = '/dev/ttyACM1'
LOG = '/home/host/opikernel/pvrgl-work/sercap_go.log'
PLUG = '/home/host/smartplug.py'

def log(s):
    ts = time.strftime('%H:%M:%S')
    line = f'[{ts}] {s}'
    print(line)
    with open('/home/host/opikernel/pvrgl-work/boot_v5.log', 'a') as f:
        f.write(line + '\n')

def rln(fd, timeout=8):
    data = b''
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            d = os.read(fd, 4096)
            if d:
                data += d
                break
        elif data:
            break
    return data

def wln(fd, s):
    os.write(fd, (s + '\r\n').encode())
    log('SENT: ' + s)

def wait_tty():
    """Poll until ttyACM1 exists and is openable."""
    log('Waiting for ttyACM1...')
    for i in range(30):
        if os.path.exists(TTY):
            # Extra settle time after USB reenumeration
            time.sleep(5)
            try:
                fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
                os.close(fd)
                log(f'ttyACM1 ready after {i+6}s')
                return True
            except OSError as e:
                log(f'ttyACM1 exists but open failed: {e}, retrying...')
        time.sleep(1)
    log('ttyACM1 never ready')
    return False

def drain(fd):
    """Drain any stale data from serial fd."""
    count = 0
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            os.read(fd, 4096)
            count += 1
        else:
            break
    if count:
        log(f'Drained {count} stale reads')

def main():
    open(LOG, 'wb').close()
    open('/home/host/opikernel/pvrgl-work/boot_v5.log', 'w').close()

    # Drain current serial state
    try:
        fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
        drain(fd)
        os.close(fd)
    except OSError:
        pass

    # Power cycle
    log('Power OFF...')
    subprocess.run(['python3', PLUG, 'off'], capture_output=True)
    time.sleep(8)
    log('Power ON...')
    subprocess.run(['python3', PLUG, 'on'], capture_output=True)

    # Wait for ttyACM1 to reappear and settle
    if not wait_tty():
        log('FAILED: ttyACM1 not ready')
        return

    # Re-open serial
    fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
    log(f'Opened {TTY}')

    # Drain early boot messages
    drain(fd)
    time.sleep(3)

    # Capture early boot for 10s
    d = rln(fd, 10)
    open(LOG, 'ab').write(d)
    log(f'Early boot: {len(d)} bytes')

    # Wait for U-Boot "Hit any key"
    log('Waiting for U-Boot prompt...')
    deadline = time.time() + 30
    while time.time() < deadline:
        d = rln(fd, 5)
        if d:
            open(LOG, 'ab').write(d)
            t = d.decode('utf-8', errors='replace')
            log(repr(t[:80]))
            if 'Hit any key' in t:
                log('INTERCEPTED!')
                break
        os.write(fd, b'\r\n')
        time.sleep(1)
    else:
        log('No "Hit any key" seen, trying anyway...')

    # Vendor kernel: ext4load uImage (26MB, ~12s) + DTB (213KB, ~15s) + bootm
    log('Loading vendor uImage...')
    wln(fd, 'ext4load mmc 0:1 0x41000000 boot/uImage')
    time.sleep(12)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  uImage: {len(d)} bytes')

    log('Loading vendor DTB at 0x43000000...')
    wln(fd, 'ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb')
    time.sleep(15)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  DTB: {len(d)} bytes')

    # NO setenv bootargs — vendor kernel has built-in bootargs + initrd
    log('Executing bootm (vendor, built-in bootargs)...')
    wln(fd, 'bootm 0x41000000 - 0x43000000')

    # Monitor kernel boot
    log('Monitoring kernel boot (100s)...')
    deadline = time.time() + 100
    login_seen = False
    while time.time() < deadline:
        d = rln(fd, 5)
        if d:
            open(LOG, 'ab').write(d)
            t = d.decode('utf-8', errors='replace')
            log(repr(t[:200]))
            tl = t.lower()
            if 'login' in tl:
                log('*** LOGIN DETECTED ***')
                login_seen = True
                break
            if 'panic' in tl:
                log('*** PANIC ***')
                break
        os.write(fd, b'\r')

    os.close(fd)

    # Check log
    with open(LOG, 'rb') as f:
        txt = f.read().decode('utf-8', errors='replace')
    log(f'Total serial log: {len(txt)} chars')

    if login_seen:
        log('Board booted! Testing SSH...')
        r = subprocess.run(
            ['sshpass', '-p', 'orangepi', 'ssh', '-o', 'StrictHostKeyChecking=accept-new',
             '-o', 'ConnectTimeout=10', 'orangepi@192.168.0.151', 'hostname; uptime'],
            capture_output=True, text=True, timeout=15
        )
        log(f'SSH stdout: {r.stdout.strip()}')
        log(f'SSH stderr: {r.stderr.strip()}')
    else:
        log('NO LOGIN. LAST 2000:')
        log(txt[-2000:])

if __name__ == '__main__':
    main()
