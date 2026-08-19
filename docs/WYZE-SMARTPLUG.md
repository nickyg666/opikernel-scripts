# WYZE-SMARTPLUG.md — power control and Wyze local access

## Purpose
Remote power-cycle of the Orange Pi Zero 3W board (recovery / automated boot tests).

## Host scripts
- `/home/tab/smartplug.py` — power on/off/toggle for Wyze plugs behind local firewall rules
- `.venv-wyze` — Python env for smartplug (host)
- Wyze creds live in the venv/config (redacted from docs) — recoverable from those files if needed

## Device
- Plug device id: `D03F271583AE`
- Wyze local rules in iptables `main` table, priorities 300–306 (watchdog + plug access)
- Power-cycle recipe (proven):
  `python3 /home/tab/smartplug.py <device> off && sleep 3 && python3 /home/tab/smartplug.py <device> on`

## Recovery playbook (REMEMBER THIS)
1. Start root serial capture on watcher (see WATCHER-SERIAL.md)
2. Smart-plug cycle the board
3. Wait for boot; check SSH `uname -r`, `uptime`; no panic in serial log
4. This recovered the board permanently (current running kernel 6.18.19+, stable for hours)

## Certificates
- CA bundle updated previously for Wyze Denver/device TLS — keep in mind if plug starts failing
  (walnut CA / denver TLS first suspect)
- If smartplug starts erroring on TLS: check venv CA bundle, rules 300–306, and plug reachability

## Fallback host
- User-offered migration target: `host@192.168.0.168:/home/host/opikernel` (mkdir first; sudo pw `1`)
  — NOT needed so far; only if host resources are exhausted.