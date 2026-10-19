#!/bin/bash
# PA bounded action 22:21 — canonical-queue integrity + kanban parity + freecode pool state
F=/home/host/opikernel/agentic-pool/BACKLOG.md
echo "== A. BACKLOG =="
ls -l --time-style=+%m-%d_%H:%M:%S "$F" | awk '{print $5" B  "$6}'
md5sum "$F"
echo "headings=$(grep -cE '^### BL-' "$F") status=$(grep -cE '^status:' "$F") claimed=$(grep -cE '^claimed-by:' "$F") escaped=$(grep -cE '^### ###' "$F")"
echo "== B. per-block anomalies (awk) =="
awk '
/^### BL-/ { if (blk!="" && (st!=1 || cb>1)) printf "ANOM %s status=%d claimed_by=%d\n", id, st, cb;
             blk="x"; id=$0; st=0; cb=0; next }
/^status:/ { if (blk!="") st++ }
/^claimed-by:/ { if (blk!="") cb++ }
END { if (blk!="" && (st!=1 || cb>1)) printf "ANOM %s status=%d claimed_by=%d\n", id, st, cb }
' "$F" | sed 's/### BL-/BL-/'
echo "== C. KANBAN (table=tasks) =="
sqlite3 /home/host/.hermes/kanban.db "select status,count(*) from tasks group by status;" 2>&1
echo "-- dup idempotency_key among backlog:* --"
sqlite3 /home/host/.hermes/kanban.db "select count(*) from (select idempotency_key from tasks where idempotency_key like 'backlog:%' group by idempotency_key having count(*)>1);" 2>&1
echo "-- dup titles --"
sqlite3 /home/host/.hermes/kanban.db "select count(*) from (select title from tasks group by title having count(*)>1);" 2>&1
echo "== D. board =="
ping -c1 -W1 192.168.0.151 >/dev/null 2>&1 && echo .151=UP || echo .151=DOWN
echo "== E. omniroute combos =="
sqlite3 /var/lib/omniroute/storage.sqlite "select name,length(data),typeof(data),updated_at from combos;" 2>&1
echo "-- freecode hops --"
sqlite3 /var/lib/omniroute/storage.sqlite "select data from combos where name in ('freecode','omni/freecode');" 2>&1 | python3 -c "
import sys,json
raw=sys.stdin.read().strip()
if not raw: print('freecode: NO ROW'); raise SystemExit
d=json.loads(raw)
ms=d.get('models') or d.get('data',{}).get('models') or []
print('top-keys:',sorted(d.keys()))
print('models:',len(ms))
for m in ms[:40]:
    print('  ',m if isinstance(m,str) else (m.get('id') or m.get('provider') or m))
" 2>&1 | head -50
