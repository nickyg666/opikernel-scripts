#!/usr/bin/env python3
"""Serial boot: auto-detect ttyACM, intercept U-Boot, boot vendor kernel.
Reads ALL serial output into a file for debugging."""
import os, time, subprocess, select

TTY = None
LOG = '/home/host/opikernel/pvrgl-work/sercap_go.log'
PLUG = '/home/host/smartplug.py'

def find_tty():
    for tty in ['/dev/ttyACM0', '/dev/ttyACM1']:
        if os.path.exists(tty):
            try:
                fd = os.open(tty, os.O_RDWR | os.O_NOCTTY)
                os.close(fd)
                return tty
            except OSError:
                pass
    return None

def log(s):
    ts = time.strftime('%H:%M:%S')
    line = f'[{ts}] {s}\n'
    print(line, end='', flush=True)

def read_chunk(fd, timeout=2):
    data = b''
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            d = os.read(fd, 4096)
            if d:
                data += d
                break
        elif data:
            break
    return data

def send(fd, cmd):
    cmd_bytes = (cmd + '\r\n').encode()
    os.write(fd, cmd_bytes)
    print(f'[{time.strftime("%H:%M:%S")}] SENT: {cmd}', flush=True)

def main():
    global TTY
    open(LOG, 'wb').close()
    log('=== AUTO BOOT START ===')

    # Find tty
    TTY = find_tty()
    if TTY:
        log(f'Found tty: {TTY}')
        try:
            fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
            while True:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r: os.read(fd, 4096)
                else: break
            os.close(fd)
        except OSError:
            TTY = None

    # Power cycle
    log('Power OFF...')
    subprocess.run(['python3', PLUG, 'off'], capture_output=True)
    time.sleep(8)
    log('Power ON...')
    subprocess.run(['python3', PLUG, 'on'], capture_output=True)

    # Wait for tty
    log('Waiting for tty...')
    for i in range(30):
        if os.path.exists('/dev/ttyACM0'):
            try:
                fd = os.open('/dev/ttyACM0', os.O_RDWR | os.O_NOCTTY)
                TTY = '/dev/ttyACM0'
                break
            except OSError:
                pass
        if os.path.exists('/dev/ttyACM1'):
            try:
                fd = os.open('/dev/ttyACM1', os.O_RDWR | os.O_NOCTTY)
                TTY = '/dev/ttyACM1'
                break
            except OSError:
                pass
        time.sleep(1)
    else:
        log('FAIL: no tty')
        return

    time.sleep(5)  # settle
    fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
    log(f'Opened {TTY}')

    # Drain early
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r: os.read(fd, 4096)
        else: break

    # Wait 3s then capture BOOT0
    time.sleep(3)
    d = read_chunk(fd, 10)
    open(LOG, 'ab').write(d)
    log(f'Early: {len(d)} bytes')

    # Wait for "Hit any key"
    log('Waiting for U-Boot...')
    deadline = time.time() + 30
    while time.time() < deadline:
        d = read_chunk(fd, 3)
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

    # Load uImage (26MB, ~12s)
    log('Loading uImage...')
    send(fd, 'ext4load mmc 0:1 0x41000000 boot/uImage')
    time.sleep(12)
    d = read_chunk(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  uImage response: {len(d)} bytes')

    # Load DTB
    log('Loading DTB...')
    send(fd, 'ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb')
    time.sleep(15)
    d = read_chunk(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  DTB response: {len(d)} bytes')

    # bootm
    log('bootm...')
    send(fd, 'bootm 0x41000000 - 0x43000000')

    # Monitor
    log('Monitoring kernel (120s)...')
    deadline = time.time() + 120
    login = False
    while time.time() < deadline:
        d = read_chunk(fd, 5)
        if d:
            open(LOG, 'ab').write(d)
            t = d.decode('utf-8', errors='replace')
            log(repr(t[:150]))
            tl = t.lower()
            if 'login' in tl:
                log('*** LOGIN ***')
                login = True
                break
            if 'panic' in tl:
                log('*** PANIC ***')
                break
        try:
            os.write(fd, b'\r')
        except OSError:
            log('TTY lost')
            break

    try:
        os.close(fd)
    except OSError:
        pass

    with open(LOG, 'rb') as f:
        txt = f.read().decode('utf-8', errors='replace')
    print(f'Serial log: {len(txt)} chars', flush=True)

    if login:
        print('SSH test...', flush=True)
        r = subprocess.run(
            ['sshpass', '-p', 'orangepi', 'ssh', '-o', 'StrictHostKeyChecking=accept-new',
             '-o', 'ConnectTimeout=10', 'orangepi@192.168.0.151', 'hostname; uptime'],
            capture_output=True, text=True, timeout=15
        )
        print(f'SSH: {r.stdout.strip() or r.stderr.strip()}', flush=True)
    else:
        print('NO LOGIN. Last 2000:', flush=True)
        print(txt[-2000:], flush=True)

    log('=== AUTO BOOT END ===')

if __name__ == '__main__':
    main()
