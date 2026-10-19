#!/bin/bash
# PA bounded tick audit: deploy hang, serial reader, queue lint, kanban sync, artifact identity
cd /home/host/opikernel || exit 1
echo "=== NOW ==="; date -u '+%Y-%m-%dT%H:%M:%SZ'; date '+%m-%d_%H:%M:%S %Z'
echo "=== DEPLOY / SERIAL ==="
pgrep -af ymodem_deploy_73.py || echo "deploy: NOT RUNNING"
pgrep -af serial_single_owner || echo "serial_owner: NOT RUNNING"
sudo fuser -v /dev/ttyACM1 2>&1 | head -5
ls -l --time-style=+%m-%d_%H:%M:%S pvrgl-work/ymodem_deploy.log pvrgl-work/sercap_room_live.log 2>&1
echo "--- tail deploy log ---"; tail -3 pvrgl-work/ymodem_deploy.log 2>&1
echo "--- tail live serial ---"; tail -3 pvrgl-work/sercap_room_live.log 2>&1
echo "=== QUEUE ==="
md5sum agentic-pool/BACKLOG.md
python3 scripts/backlog-section-lint.py 2>&1 | tail -5
echo "=== KANBAN ==="
python3 - <<'PY'
import sqlite3
c=sqlite3.connect('file:/home/host/.hermes/kanban.db?mode=ro',uri=True)
rows=c.execute("select id,status,assignee,title from tasks where status in ('in_progress','ready') order by status,assignee").fetchall()
print("in_progress/ready rows:",len(rows))
for r in rows: print(" ",r[0],r[1],repr(r[2]),str(r[3])[:60])
PY
echo "=== IMAGE ==="
md5sum arch/arm64/boot/Image 2>/dev/null || md5sum /home/host/kernel-trees/host-build/mainline-7.3/arch/arm64/boot/Image
