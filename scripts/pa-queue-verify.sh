#!/bin/bash
# PA bounded verify: queue header integrity + probe agreement (one chain)
cd /home/host/opikernel || exit 1
echo "=== guard --check (live) ==="
python3 scripts/backlog-lastgood-guard.py --check
echo "guard rc=$?"
echo "=== three probes must agree ==="
printf "strict: claimed=%s blocked=%s done=%s\n" \
  "$(grep -c '^status: claimed' agentic-pool/BACKLOG.md)" \
  "$(grep -c '^status: blocked' agentic-pool/BACKLOG.md)" \
  "$(grep -c '^status: done' agentic-pool/BACKLOG.md)"
printf "loose : %s\n" "$(awk -F': ' '/status:/{c[$2]++} END{printf "claimed=%d blocked=%d done=%d", c["claimed"], c["blocked"], c["done"]}' agentic-pool/BACKLOG.md)"
python3 scripts/backlog-section-lint.py 2>&1 | tail -3
printf "orphans_above_first_item=%s\n" "$(awk '/^### BL-/{exit} /^status:/{n++} END{print n+0}' agentic-pool/BACKLOG.md)"
printf "status_lines=%s item_blocks=%s\n" "$(grep -c '^status:' agentic-pool/BACKLOG.md)" "$(grep -c '^### BL-' agentic-pool/BACKLOG.md)"
# attribution: 'claims:' is an ALIAS of 'claimed-by:' (BL-15 used it and every
# keyed-on-claimed-by probe read the board as 20/24). 'held-by:' = consent-held
# (owner is the room, not an agent) and 'attribution:' = explicitly acknowledged
# unattributed. All four count as accounted-for; only a second OWNER key is a
# MULTI-ATTRIB defect, and only a block with none of the four is NO-ATTRIB.
python3 - <<'PY'
import re
t=open('agentic-pool/BACKLOG.md').read()
parts=re.split(r'^### (BL-\d+)', t, flags=re.M)
rows=[]
for i in range(1,len(parts),2):
    body=parts[i+1]
    st=re.search(r'^status:\s*(\S+)', body, re.M)
    own=len(re.findall(r'^(?:claimed-by|claims):', body, re.M))
    hold=len(re.findall(r'^held-by:', body, re.M))
    flag=len(re.findall(r'^attribution:', body, re.M))
    rows.append((parts[i], st.group(1) if st else '?', own, hold, flag))
multi=[r for r in rows if r[2]>1]
none =[r for r in rows if (r[2]+r[3]+r[4])==0]
print("attrib_lines=%d blocks=%d multi=%d none=%d held=%d flagged=%d" % (
    sum(r[2]+r[3]+r[4] for r in rows), len(rows), len(multi), len(none),
    sum(1 for r in rows if r[3]), sum(1 for r in rows if r[4])))
if multi: print("MULTI-ATTRIB:", [(r[0],r[2]) for r in multi])
if none:  print("NO-ATTRIB:", [(r[0],r[1]) for r in none])
PY
md5sum agentic-pool/BACKLOG.md agentic-pool/BACKLOG.md.lastgood
echo "=== kanban mirror ==="
sqlite3 -readonly /home/host/.hermes/kanban.db "select status,count(*) from tasks group by status;" 2>&1
