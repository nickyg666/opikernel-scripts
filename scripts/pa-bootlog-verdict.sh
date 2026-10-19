#!/bin/bash
# PA bounded action: verdict the newest capture in sercap_room_live.log
cd /home/host/opikernel/pvrgl-work || exit 1
L=sercap_room_live.log
ls -l --time-style=+%m-%d_%H:%M:%S "$L"
sleep 5
ls -l --time-style=+%m-%d_%H:%M:%S "$L"
echo "== HOLDER =="
fuser /dev/opiz3w-serial 2>&1
for pid in $(fuser /dev/opiz3w-serial 2>/dev/null); do ps -o pid,etime,stat,cmd -p "$pid" | tail -1; done
date '+now=%m-%d %H:%M:%S'
echo "== LEASE =="
python3 - <<'PY'
import json,datetime
d=json.load(open('board.lease.json'))
print(d['owner'], datetime.datetime.fromtimestamp(d['ts']).strftime('%m-%d %H:%M:%S'), 'ttl', d['ttl'])
PY
echo "== MARKERS (count over whole log) =="
for p in 'Linux version' 'PARTUUID=486ea4ae' 'VFS: Cannot open root' 'Kernel panic' 'mmcblk1' 'powervr' 'rogue' 'systemd' 'login:' 'EXT4-fs' 'opi_root' 'mmc: mmc' 'sunxi-mmc' 'Starting kernel'; do
  printf '%-26s %s\n' "$p" "$(strings "$L" | grep -c "$p")"
done
echo "== LAST 70 LINES =="
strings "$L" | tail -70
