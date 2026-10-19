#!/bin/bash
# Nightly archive replication: NAS(4tb_bad200) -> DAS(free3t)
LOG=/home/host/opikernel/logs/archive-sync.log
# Credentials live OUTSIDE this repo: /home/host/.secrets/nas.env (0600).
[ -r /home/host/.secrets/nas.env ] && . /home/host/.secrets/nas.env
{
echo "=== $(date -Is) sync start"
sshpass -p "$NAS_PW" ssh -F /dev/null -o ConnectTimeout=15 nas@192.168.0.11 \
  "rsync -a --delete --info=stats1 -e 'ssh -F /dev/null -o StrictHostKeyChecking=accept-new' /mnt/4tb_bad200/opiz3w-archive/ das@192.168.0.9:/mnt/free3t/opiz3w-archive/" \
  && echo "=== OK" || echo "=== FAIL rc=$?"
} >> "$LOG" 2>&1
