#!/bin/bash
# TR bounded action 22:33 — queue integrity + card/board state, one shot.
cd /home/host/opikernel || exit 1
echo "== QUEUE =="
ls -l --time-style=+%m-%d_%H:%M:%S agentic-pool/BACKLOG.md
md5sum agentic-pool/BACKLOG.md
h=$(grep -c '^### BL-' agentic-pool/BACKLOG.md)
s=$(grep -c '^status:' agentic-pool/BACKLOG.md)
esc=$(grep -c '^### ###' agentic-pool/BACKLOG.md)
echo "headings=$h status=$s escaped=$esc"
echo "== CLAIM OWNERS ON BOOT ITEMS =="
grep -n -A3 '^### BL-16' agentic-pool/BACKLOG.md | head -8
echo "== LIVE =="
ping -c1 -W2 192.168.0.151 >/dev/null 2>&1 && echo "board .151 UP" || echo "board .151 DOWN"
ping -c1 -W2 192.168.0.149 >/dev/null 2>&1 && echo "tab .149 UP" || echo "tab .149 DOWN"
echo "== STAGED MD5 =="
md5sum stage/7.3-stage/boot/mainline/Image stage/7.3-stage/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
