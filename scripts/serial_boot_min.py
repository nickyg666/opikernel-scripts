#!/usr/bin/env python3
"""Minimal serial boot: open ttyACM1, power cycle, boot vendor kernel."""
import os, time, subprocess, select

TTY = '/dev/ttyACM1'
LOG = '/home/host/opikernel/pvrgl-work/sercap_go.log'

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
    print('SENT: ' + s)

def main():
    open(LOG, 'wb').close()
    fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
    print('Opened', TTY)

    # drain
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r: os.read(fd, 4096)
        else: break

    print('Power off...')
    subprocess.run(['python3', '/home/host/smartplug.py', 'off'])
    time.sleep(8)
    print('Power on...')
    subprocess.run(['python3', '/home/host/smartplug.py', 'on'])
    print('Reading BOOT0...')
    time.sleep(4)
    d = rln(fd, 10)
    open(LOG, 'ab').write(d)
    print('Got', len(d), 'bytes')

    print('Waiting for U-Boot...')
    deadline = time.time() + 25
    while time.time() < deadline:
        d = rln(fd, 5)
        if d:
            open(LOG, 'ab').write(d)
            t = d.decode('utf-8', errors='replace')
            print(repr(t[:80]))
            if 'Hit any key' in t:
                print('INTERCEPTED!')
                break
        # send breaks
        os.write(fd, b'\r\n')
        time.sleep(1)

    print('Loading uImage...')
    wln(fd, 'ext4load mmc 0:1 0x41000000 boot/uImage')
    time.sleep(8)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    print('DTB...')
    wln(fd, 'ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb')
    time.sleep(4)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)

    print('bootargs...')
    wln(fd, 'setenv bootargs root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm console=ttyS0,115200')
    time.sleep(1)

    print('bootm...')
    wln(fd, 'bootm 0x41000000 - 0x43000000')

    print('Monitoring (80s)...')
    deadline = time.time() + 80
    while time.time() < deadline:
        d = rln(fd, 5)
        if d:
            open(LOG, 'ab').write(d)
            t = d.decode('utf-8', errors='replace')
            print(repr(t[:200]))
            tl = t.lower()
            if 'login' in tl:
                print('*** LOGIN DETECTED ***')
                break
            if 'panic' in tl:
                print('*** PANIC ***')
                break

    os.close(fd)
    with open(LOG, 'rb') as f:
        txt = f.read().decode('utf-8', errors='replace')
    print('Log size:', len(txt), 'chars')
    if 'login' not in txt.lower():
        print('LAST 2000:')
        print(txt[-2000:])

    # SSH test
    r = subprocess.run(
        ['sshpass', '-p', 'orangepi', 'ssh', '-o', 'StrictHostKeyChecking=accept-new',
         '-o', 'ConnectTimeout=5', 'orangepi@192.168.0.151', 'hostname; uptime'],
        capture_output=True, text=True, timeout=10
    )
    print('SSH:', r.stdout.strip(), r.stderr.strip())

if __name__ == '__main__':
    main()
