#!/usr/bin/env python3
"""Serial boot: try vendor kernel, diagnose DTB issue, boot without if needed.
Key: DTB may be corrupt on SD. Try loading at alternate address, verify bytes,
then boot and capture kernel panic to diagnose root cause."""
import os, time, subprocess, select

TTY = '/dev/ttyACM0'
LOG = '/home/host/opikernel/pvrgl-work/sercap_go.log'
PLUG = '/home/host/smartplug.py'

def log(s):
    ts = time.strftime('%H:%M:%S')
    line = f'[{ts}] {s}\n'
    print(line, end='', flush=True)
    with open('/home/host/opikernel/pvrgl-work/boot_diag.log', 'a') as f:
        f.write(line)

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
    try:
        os.write(fd, (s + '\r\n').encode())
        log('SENT: ' + s)
    except OSError:
        log(f'WRITE FAILED: {s}')

def wait_tty(settle=5):
    log(f'Waiting for {TTY}...')
    for i in range(30):
        if os.path.exists(TTY):
            time.sleep(settle)
            try:
                fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
                os.close(fd)
                log(f'{TTY} ready')
                return True
            except OSError:
                pass
        time.sleep(1)
    return False

def drain(fd):
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r: os.read(fd, 4096)
        else: break

def monitor(fd, deadline):
    """Monitor for login/panic, handle tty drops gracefully."""
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
                return True
            if 'panic' in tl:
                log('*** PANIC ***')
                return False
        # Heartbeat — safe write, ignore errors
        try:
            os.write(fd, b'\r')
        except OSError:
            log('TTY write failed (dropped?)')
    return login_seen

def main():
    open(LOG, 'wb').close()
    open('/home/host/opikernel/pvrgl-work/boot_diag.log', 'w').close()
    log('=== DIAG BOOT START ===')

    # Drain current serial
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

    if not wait_tty(settle=5):
        log('FAIL: tty not ready')
        return

    fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
    log(f'Opened {TTY}')
    drain(fd)

    time.sleep(3)
    d = rln(fd, 10)
    open(LOG, 'ab').write(d)
    log(f'Early: {len(d)} bytes')

    # Intercept U-Boot
    log('Waiting for U-Boot...')
    deadline = time.time() + 30
    while time.time() < deadline:
        d = rln(fd, 5)
        if d:
            open(LOG, 'ab').write(d)
            t = d.decode('utf-8', errors='replace')
            if 'Hit any key' in t:
                log('INTERCEPTED!')
                break
        try:
            os.write(fd, b'\r\n')
        except OSError:
            pass
        time.sleep(1)

    # Load uImage
    log('Loading uImage at 0x41000000...')
    wln(fd, 'ext4load mmc 0:1 0x41000000 boot/uImage')
    time.sleep(12)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  uImage: {len(d)} bytes')

    # Try DTB at 0x43000000 (vendor DTB, no suffix)
    log('Loading vendor DTB at 0x43000000 (no suffix)...')
    wln(fd, 'ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb')
    time.sleep(15)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  DTB (no suffix): {len(d)} bytes')

    # If DTB at 0x43000000 returned 0, try .orig-0810-0015 at same addr
    if len(d) == 0:
        log('DTB failed at 0x43000000 (no suffix). Trying .orig-0810-0015 at 0x45000000...')
        wln(fd, 'ext4load mmc 0:1 0x45000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015')
        time.sleep(15)
        d2 = rln(fd, 3)
        open(LOG, 'ab').write(d2)
        log(f'  DTB (.orig-0810-0015) at 0x45000000: {len(d2)} bytes')
        dtb_addr = '0x45000000' if len(d2) > 0 else None
    else:
        dtb_addr = '0x43000000'

    # Try bootm, with or without DTB
    if dtb_addr:
        log(f'bootm (with DTB at {dtb_addr})...')
        wln(fd, f'bootm 0x41000000 - {dtb_addr}')
    else:
        log('DTB failed twice. Trying bootm WITHOUT DTB (let kernel find its own)...')
        wln(fd, 'bootm 0x41000000')

    # Monitor kernel boot
    log('Monitoring kernel (120s)...')
    deadline = time.time() + 120
    login_seen = monitor(fd, deadline)

    # Close carefully
    try:
        os.close(fd)
    except OSError:
        log('TTY already closed')

    # Check serial log
    with open(LOG, 'rb') as f:
        txt = f.read().decode('utf-8', errors='replace')
    log(f'Serial log: {len(txt)} chars')

    if login_seen:
        log('SSH test...')
        r = subprocess.run(
            ['sshpass', '-p', 'orangepi', 'ssh', '-o', 'StrictHostKeyChecking=accept-new',
             '-o', 'ConnectTimeout=10', 'orangepi@192.168.0.151', 'hostname; uptime'],
            capture_output=True, text=True, timeout=15
        )
        log(f'SSH: {r.stdout.strip() or r.stderr.strip()}')
    else:
        log('NO LOGIN. Key section from serial log:')
        # Show kernel boot section
        for kw in ['Booting kernel', 'Starting kernel', 'VFS', 'DTB', 'panic', 'Mounting', 'EXT4-fs']:
            idx = txt.rfind(kw)
            if idx >= 0:
                log(f'  [{kw}]: ...{txt[max(0,idx-50):idx+300]}...')
                break
        else:
            log('  LAST 2000: ' + txt[-2000:])

    log('=== DIAG BOOT END ===')

if __name__ == '__main__':
    main()
