#!/bin/bash
# Capture a boot and emit a verdict file. Detached; poll the marker, not the board.
# Nick 2026-10-03: "do the things" + "don't end turns on a poll".
LOG=/home/host/opikernel/state/watch-boot.log
OUT=/home/host/opikernel/state/watch-verdict.txt
DEV=/dev/opiz3w-serial
[ -e "$DEV" ] || DEV=$(ls /dev/ttyACM* 2>/dev/null | head -1)

BOARD_LEASE_OWNER=KernelDev-GPU timeout 120 python3 /home/host/smartplug.py cycle >/dev/null 2>&1

python3 - "$DEV" "$LOG" "$OUT" <<'PY'
import re, sys, time
import serial
dev, log, out = sys.argv[1], sys.argv[2], sys.argv[3]
s = serial.Serial(dev, 115200, timeout=0.4)
s.reset_input_buffer()
acc = b''
t0 = time.time()
while time.time() - t0 < 300:
    try:
        c = s.read(65536)
        if c: acc += c
    except Exception:
        pass
s.close()
open(log, 'wb').write(acc)
t = acc.decode('utf-8', 'replace')
def n(p): return len(re.findall(p, t, re.I))
verdict = [
    "bytes=%d" % len(acc),
    "last_ts=%s" % (re.findall(r'\[\s*(\d+\.\d+)\]', t)[-1] if re.findall(r'\[\s*(\d+\.\d+)\]', t) else '?'),
    "duplicate_ccu=%d" % n('duplicate filename'),
    "oops_brk=%d" % n('Oops - BRK'),
    "unexpected_daif=%d" % n('Unexpected DAIF'),
    "kernel_panic=%d" % n('Kernel panic'),
    "login_prompt=%d" % n(r'login:'),
    "scandone_probe=%d" % n('scandone:'),
    "scancfm=%d" % n('scancfm:'),
    "scanres=%d" % n('scanres:'),
    "scanu_results_idx4=%d" % len(re.findall(r'id=4100 task=4 idx=4', t)),
    "iw_bss=%d" % n(r'^BSS '),
]
open(out, 'w').write('\n'.join(verdict) + '\n')
print('\n'.join(verdict))
PY
