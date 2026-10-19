#!/bin/bash
# PA I2 negative test: duplicate state line => guard must refuse to snapshot and repair the header.
# Mutates the live file for <2s, then asserts byte-restore. Corpse/backups preserved.
set -u
cd /home/host/opikernel || exit 1
L=agentic-pool/BACKLOG.md
GOOD=a6aecc1a9726d025c3bf5e1844f5a30a
cp -p "$L" "$L.negtest-backup-$(date +%Y%m%d-%H%M%S)"
python3 - <<'PY'
import pathlib
p = pathlib.Path("/home/host/opikernel/agentic-pool/BACKLOG.md")
t = p.read_text()
h = t.split("\n### BL-", 1)[0]
p.write_text(t.replace(h, h + "status: claimed\nclaimed-by: negtest\n", 1))
PY
echo "mutated: $(md5sum $L | cut -c1-32) orphans=$(awk '/^### BL-/{exit} /^status:/{n++} END{print n+0}' $L)"
python3 scripts/backlog-lastgood-guard.py --check
echo "guard rc=$?"
echo "restored: $(md5sum $L | cut -c1-32)"
if [ "$(md5sum $L | cut -d' ' -f1)" = "$GOOD" ]; then echo "I2 TEST PASS (byte-restored to last-good)"; else echo "I2 TEST FAIL"; fi
