# WATCHER-SERIAL.md — watcher box, serial console, capture

## Watcher box
- IP `192.168.0.167`, user/pass `orangepi/orangepi`, sudo via `echo orangepi | sudo -S`
- Job: serial console access to the Orange Pi Zero 3W board + (historically) MangoPi Mi Infinity3S

## The /dev/ttyS0 gotcha (IMPORTANT)
- `/dev/ttyS0` on watcher is owned `root:tty`, mode `crw--w----` (0600).
- Non-root `cat /dev/ttyS0` FAILS SILENTLY on first read → looked like the board "stopped printing
  at 22s / panicked". It never panicked; the catcher lost the port.
- ALWAYS launch capture as root:
  `echo orangepi | sudo -S setsid bash -c 'stty -F /dev/ttyS0 230400 raw; exec cat /dev/ttyS0' >> /home/orangepi/uart_capture/ttyS0.log 2>&1 &`
- Verify capture is alive: log file mtime keeps updating; `pgrep -f "cat /dev/ttyS0"`.

## Capture files on watcher
- Live log: `/home/orangepi/uart_capture/ttyS0.log` (grows)
- Legacy boot captures: `boot_cap*.txt`, `uboot_boot_*.sh`, `uboot_catch.sh` — stale but don't delete
- Boot scripts pattern used during panic hunt: run splash/echo markers, wait N s, kill cat, save log

## Using serial for board work
- Board serial output: 230400 8N1 on ttyS0 (USB-UART adapter)
- To follow an interactive serial session from a terminal: use the live log tail.
- NEVER restart the capture during a board boot if you want the full log.

## Notes
- The 22s "panic" mystery: resolved — see BOARD-RECOVERY.md. Don't re-litigate.
- Watch for other devices on the same serial adapter (Mi Infinity3S) — port is shared historically;
  confirm current cable attachment before assuming console identity.