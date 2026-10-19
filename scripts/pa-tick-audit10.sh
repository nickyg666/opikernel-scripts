#!/bin/bash
K=/home/host/.hermes/kanban.db
cd /home/host/opikernel || exit 1
echo "=== A. kanban rows for BL-13 / BL-19 (fresh) ==="
sqlite3 -readonly "$K" "select id||' | '||status||' | '||coalesce(assignee,'-')||' | '||datetime(created_at/1000,'unixepoch')||' | '||substr(title,1,50) from tasks where title like 'BL-13%' or title like 'BL-19%';"
echo
echo "=== B. who touched BL-13 / BL-19 in the pool? (name+time) ==="
grep -rl 'BL-19' agentic-pool/*.md 2>/dev/null | head -8
echo "--- BL-19 mentions in files modified in the last 3h ---"
for f in $(find agentic-pool -maxdepth 1 -name '*.md' -mmin -180 | head -20); do
  c=$(grep -c 'BL-19' "$f" 2>/dev/null)
  [ "$c" != "0" ] && echo "$(ls -l --time-style=+%m-%d_%H:%M:%S "$f" | awk '{print $6,$7}') $f BL-19x$c"
done
echo "--- BL-13 mentions, files modified in last 3h ---"
for f in $(find agentic-pool -maxdepth 1 -name '*.md' -mmin -180 | head -20); do
  c=$(grep -c 'BL-13' "$f" 2>/dev/null)
  [ "$c" != "0" ] && echo "$(ls -l --time-style=+%m-%d_%H:%M:%S "$f" | awk '{print $6,$7}') $f BL-13x$c"
done
echo
echo "=== C. sync script: how status/claimed-by map ==="
grep -n 'claimed-by\|kstatus\|status.*open.*ready' scripts/sync-backlog-to-kanban.py | head -12
