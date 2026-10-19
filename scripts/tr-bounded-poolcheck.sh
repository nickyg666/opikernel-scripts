#!/bin/bash
# TelegramRunner bounded action: canonical queue integrity + kanban mirror parity.
cd /home/host/opikernel || exit 1
F=agentic-pool/BACKLOG.md
ls -l --time-style=+%m-%d_%H:%M:%S "$F"
md5sum "$F"
echo "headings=$(grep -c '^### BL-' "$F") escaped=$(awk '/^### ### BL-/{c++}END{print c+0}' "$F")"
awk '/^status:/{s[$2]++} END{for(k in s) printf "%s=%d ",k,s[k]; print ""}' "$F"
echo "--- kanban ---"
sqlite3 /home/host/.hermes/kanban.db "select status,count(*) from tasks group by 1 order by 1;"
echo "--- board reachability ---"
timeout 3 ping -c1 -W2 192.168.0.151 >/dev/null 2>&1 && echo "board151=UP" || echo "board151=DOWN"
