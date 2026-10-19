#!/usr/bin/env python3
"""Boot vendor kernel via cron: power cycle, intercept U-Boot, boot, SSH verify."""
import os, time, subprocess, select

TTY = '/dev/ttyACM1'
LOG = '/home/host/opikernel/pvrgl-work/sercap_go.log'
PLUG = '/home/host/smartplug.py'
CRON_LOG = '/home/host/opikernel/pvrgl-work/boot_cron.log'

def log(s):
    ts = time.strftime('%H:%M:%S')
    line = f'[{ts}] {s}\n'
    print(line, end='', flush=True)
    with open(CRON_LOG, 'a') as f:
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
    os.write(fd, (s + '\r\n').encode())
    log('SENT: ' + s)

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
    log(f'{TTY} never ready')
    return False

def drain(fd):
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r: os.read(fd, 4096)
        else: break

def main():
    open(LOG, 'wb').close()
    open(CRON_LOG, 'w').close()
    log('=== CRON BOOT START ===')

    # Open and drain
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

    # Capture early boot
    time.sleep(3)
    d = rln(fd, 10)
    open(LOG, 'ab').write(d)
    log(f'Early boot: {len(d)} bytes')

    # Wait for U-Boot
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
        os.write(fd, b'\r\n')
        time.sleep(1)
    else:
        log('No intercept, continuing...')

    # Vendor kernel boot sequence
    log('Loading uImage...')
    wln(fd, 'ext4load mmc 0:1 0x41000000 boot/uImage')
    time.sleep(12)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  uImage: {len(d)} bytes')

    log('Loading DTB...')
    wln(fd, 'ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb')
    time.sleep(15)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  DTB: {len(d)} bytes')

    log('bootm...')
    wln(fd, 'bootm 0x41000000 - 0x43000000')

    # Monitor kernel boot
    log('Monitoring kernel (100s)...')
    deadline = time.time() + 100
    login_seen = False
    while time.time() < deadline:
        d = rln(fd, 5)
        if d:
            open(LOG, 'ab').write(d)
            t = d.decode('utf-8', errors='replace')
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
        log('NO LOGIN. LAST 1000:')
        log(txt[-1000:])

    log('=== CRON BOOT END ===')

if __name__ == '__main__':
    main()
