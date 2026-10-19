#!/bin/bash
cd /home/host/opikernel/pvrgl-work
echo "=== exact classifier strings in the AUTHORITATIVE log ==="
for m in 'Linux version' 'Waiting for root device' 'sunxi_bsp_pinctrl_init_with_variant' 'sunxi pinctrl version'; do
  printf '%-40s %s\n' "$m" "$(grep -c "$m" sercap_manual_earlycon.log 2>/dev/null)"
done
echo
echo "=== file identity (crc + size + mtime) ==="
md5sum sercap_manual_earlycon.log
stat -c 'size=%s mtime=%y' sercap_manual_earlycon.log
echo
echo "=== last 3 va39-gate-watch executions ==="
python3 - <<'PY'
import sqlite3
con = sqlite3.connect('/home/host/.hermes/cron/executions.db')
con.row_factory = sqlite3.Row
cur = con.cursor()
tabs = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
print("tables:", tabs)
t = 'executions' if 'executions' in tabs else tabs[0]
cols = [r[1] for r in cur.execute(f"PRAGMA table_info({t})")]
print("cols:", cols)
rows = cur.execute(f"select * from {t} order by rowid desc limit 60").fetchall()
hits = 0
for r in rows:
    s = " ".join(str(v) for v in tuple(r))
    if 'gate' in s.lower() and 'va39' in s.lower():
        print("----")
        for c, v in zip(cols, tuple(r)):
            print(f"  {c}: {str(v)[:400]}")
        hits += 1
        if hits >= 3:
            break
if not hits:
    print("no va39-gate-watch rows in last 60; dumping 5 most recent generally")
    for r in rows[:5]:
        for c, v in zip(cols, tuple(r)):
            print(f"  {c}: {str(v)[:200]}")
        print("----")
PY
