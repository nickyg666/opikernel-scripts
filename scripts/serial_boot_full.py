#!/usr/bin/env python3
"""Serial boot: wait for ttyACM1 → power cycle → boot vendor kernel → SSH verify."""
import os, time, subprocess, select, glob

TTY = '/dev/ttyACM1'
LOG = '/home/host/opikernel/pvrgl-work/sercap_go.log'
PLUG = '/home/host/smartplug.py'

def log(s):
    print(s)
    with open('/home/host/opikernel/pvrgl-work/boot_recovery.log', 'a') as f:
        f.write(s + '\n')

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

def wait_for_tty():
    """Poll until ttyACM1 exists."""
    log('Waiting for ttyACM1...')
    for i in range(30):
        if os.path.exists(TTY):
            log(f'ttyACM1 found after {i}s')
            return True
        time.sleep(1)
    log('ttyACM1 never appeared')
    return False

def power_cycle():
    log('Power OFF...')
    subprocess.run(['python3', PLUG, 'off'], capture_output=True)
    time.sleep(8)
    log('Power ON...')
    subprocess.run(['python3', PLUG, 'on'], capture_output=True)
    time.sleep(2)
    return wait_for_tty()

def main():
    open(LOG, 'wb').close()
    
    # Ensure ttyACM1 is present
    if not os.path.exists(TTY):
        log('ttyACM1 missing, waiting...')
        if not wait_for_tty():
            return
    
    fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
    log('Opened ' + TTY)
    
    # drain stale data
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r: os.read(fd, 4096)
        else: break
    
    # Power cycle to reset board state
    os.close(fd)
    fd = None
    if not power_cycle():
        return
    
    # Re-open ttyACM1 after power cycle
    time.sleep(2)
    if not os.path.exists(TTY):
        log('ttyACM1 gone after power cycle, waiting...')
        if not wait_for_tty():
            return
    fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
    log('Re-opened ' + TTY)
    
    # drain again
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r: os.read(fd, 4096)
        else: break
    
    log('Reading early boot...')
    time.sleep(3)
    d = rln(fd, 10)
    open(LOG, 'ab').write(d)
    log(f'Got {len(d)} bytes (early boot)')
    
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
    
    log('Loading mainline Image at 0x41000000...')
    wln(fd, 'ext4load mmc 0:1 0x41000000 boot/mainline/Image')
    time.sleep(12)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  {len(d)} bytes')

    log('Loading DTB at 0x43000000 (213KB, needs ~15s)...')
    wln(fd, 'ext4load mmc 0:1 0x43000000 boot/dtb/allwinner/sun60i-a733-orangepi-zero3w.dtb.orig-0810-0015')
    time.sleep(15)
    d = rln(fd, 3)
    open(LOG, 'ab').write(d)
    log(f'  {len(d)} bytes after DTB load')

    # Use ${bootargs} append to preserve U-Boot's built-in DTB init
    # Direct bootargs causes FDT_ERR_NOSPACE when DTB at 0x43000000
    log('Setting bootargs (append mode, preserve existing)...')
    wln(fd, 'setenv bootargs ${bootargs} root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 modprobe.blacklist=aic8800_btlpm')
    time.sleep(1)

    log('Executing booti (mainline, no initrd, MMC driver must be in-kernel)...')
    wln(fd, 'booti 0x41000000 - 0x43000000')
    
    log('Monitoring kernel boot (120s)...')
    deadline = time.time() + 120
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
        # heartbeat newline
        os.write(fd, b'\r')
    
    os.close(fd)
    
    with open(LOG, 'rb') as f:
        txt = f.read().decode('utf-8', errors='replace')
    log(f'Log: {len(txt)} chars')
    
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
