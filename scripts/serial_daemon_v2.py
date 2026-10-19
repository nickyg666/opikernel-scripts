#!/usr/bin/env python3
"""Persistent serial monitor: keep ttyACM1 open, log everything, handle drops."""
import os, time, select, signal, sys

TTY = '/dev/ttyACM1'
LOG = '/home/host/opikernel/pvrgl-work/serial_persistent.log'
PIDFILE = '/home/host/opikernel/pvrgl-work/serial_daemon.pid'

def log(s, fd):
    ts = time.strftime('%H:%M:%S')
    line = f'[{ts}] {s}\n'
    print(line, end='')
    with open(LOG, 'a') as f:
        f.write(line)

def main():
    # Signal handler
    def sighandler(sig, frame):
        log('SIGTERM received, exiting', None)
        sys.exit(0)
    signal.signal(signal.SIGTERM, sighandler)
    signal.signal(signal.SIGINT, sighandler)

    # Write PID
    with open(PIDFILE, 'w') as f:
        f.write(str(os.getpid()))
    
    # Open serial
    log(f'Starting serial monitor on {TTY}', None)
    
    while True:
        fd = -1
        try:
            if not os.path.exists(TTY):
                log(f'{TTY} missing, waiting...', None)
                for i in range(30):
                    if os.path.exists(TTY):
                        log(f'{TTY} reappeared', None)
                        break
                    time.sleep(1)
                else:
                    log(f'{TTY} never returned, exiting', None)
                    break
            
            fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY)
            log(f'Opened {TTY}', None)
            
            # Drain stale
            while True:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r: os.read(fd, 4096)
                else: break
            
            # Persistent read loop
            stale_count = 0
            while True:
                r, _, _ = select.select([fd], [], [], 2)
                if r:
                    data = os.read(fd, 4096)
                    if data:
                        with open(LOG, 'ab') as f:
                            f.write(data)
                        stale_count = 0
                    else:
                        stale_count += 1
                        if stale_count > 3:
                            log('Multiple empty reads, tty may have dropped', None)
                            os.close(fd)
                            break
                else:
                    stale_count += 1
                    if stale_count > 5:
                        log('No data for 10s, tty may have dropped', None)
                        os.close(fd)
                        break
                        
        except OSError as e:
            log(f'OSError: {e}, retrying in 2s', None)
            try: os.close(fd)
            except: pass
            time.sleep(2)
        except Exception as e:
            log(f'Exception: {e}', None)
            try: os.close(fd)
            except: pass
            time.sleep(2)

if __name__ == '__main__':
    main()
