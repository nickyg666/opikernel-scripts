#!/bin/bash
# hermes_private_backup.sh — sanitized hermes-private backup + rotation
# Every 12h via crontab. Retention: 12 daily (6 days) + 1 weekly + 1 monthly = 14.
set -uo pipefail

BACKUP_DIR=/home/host/hermes-private-backups
DUMP_DIR=/home/host/hermes-private-dump
SANITIZE=/home/host/opikernel/scripts/sanitize_hermes_dump.sh
NAS_TARGET="nas@192.168.0.11:/mnt/4tb_bad200/hermes-private-backups/"
DAS_TARGET="das@192.168.0.9:/mnt/free3t/hermes-private-backups/"
# Credentials live OUTSIDE this repo: /home/host/.secrets/nas.env (0600).
[ -r /home/host/.secrets/nas.env ] && . /home/host/.secrets/nas.env
TS=$(date +%Y%m%d-%H%M%S)
TARBALL="$BACKUP_DIR/hermes-private-$TS.tar.gz"

mkdir -p "$BACKUP_DIR"
LOG=/home/host/opikernel/logs/hermes-backup.log
mkdir -p "$(dirname "$LOG")"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

log "=== backup start ==="

# 1. Build sanitized dump (rebuilds $DUMP_DIR fresh)
if ! bash "$SANITIZE" >/dev/null 2>&1; then
  log "ERROR sanitize failed — aborting"
  exit 1
fi

# 2. Tar it
tar czf "$TARBALL" -C /home/host hermes-private-dump 2>>"$LOG" || { log "ERROR tar failed"; exit 1; }
log "created $TARBALL ($(stat -c%s "$TARBALL") bytes)"

# 3. GitHub push (non-fatal if repo/network hiccups) — sanitize wipes .git, so re-init each run
if command -v git >/dev/null 2>&1 && [ -f /home/host/.git_pat_hermes ]; then
  PAT=$(tr -d '\n' < /home/host/.git_pat_hermes)
  ( cd "$DUMP_DIR" && \
    [ -d .git ] || git init -q -b main; \
    git remote remove origin 2>/dev/null; \
    git remote add origin "https://nickyg666:${PAT}@github.com/nickyg666/hermes-private.git" && \
    git add -A && \
    git -c user.name="nickyg666" -c user.email="nick@w8.mom" \
      commit -m "auto backup $(date +%Y-%m-%d_%H%M)" --quiet 2>/dev/null; \
    timeout 60 git push -q -u origin main --force ) >>"$LOG" 2>&1 \
    && log "github push ok" || log "github push skipped/failed (non-fatal)"
fi

# 4. Rotation (local): keep 12 newest daily + newest older-than-7d (weekly)
#    + newest older-than-31d (monthly) = max 14 files
rotate() {
  local dir="$1"
  local files
  mapfile -t files < <(ls -1t "$dir"/hermes-private-*.tar.gz 2>/dev/null | sort -r)
  local n=${#files[@]}
  # delete from the oldest end while keeping the policy
  local i keep=1
  for ((i = n - 1; i >= 0; i--)); do
    local f="${files[$i]}"
    local age_days
    age_days=$(awk -v ts="$(date -r "$f" +%s)" -v now="$(date +%s)" 'BEGIN{printf "%.2f", (now-ts)/86400}')
    # newest 12 are always kept (they're within the daily window)
    if (( i < 12 )); then continue; fi
    # weekly: keep the newest file older than 7 days
    if (( keep == 1 )) && awk "BEGIN{exit !($age_days > 7)}"; then keep=0; continue; fi
    # monthly: keep the newest file older than 31 days
    if (( keep == 0 )) && awk "BEGIN{exit !($age_days > 31)}"; then keep=0; continue; fi
    rm -f "$f" && log "pruned $f (age ${age_days}d)"
  done
}

rotate "$BACKUP_DIR"

# 5. Sync to NAS + DAS (mirror the pruned set; --delete keeps remote identical)
if command -v sshpass >/dev/null 2>&1; then
  sshpass -p "$NAS_PW" rsync -a --delete -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
    "$BACKUP_DIR"/ "$NAS_TARGET" >>"$LOG" 2>&1 && log "nas sync ok" || log "nas sync FAILED"
  sshpass -p "$DAS_PW" rsync -a --delete -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
    "$BACKUP_DIR"/ "$DAS_TARGET" >>"$LOG" 2>&1 && log "das sync ok" || log "das sync FAILED"
else
  log "sshpass missing — skipping NAS/DAS sync"
fi

log "=== backup done (files: $(ls -1 "$BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)) ==="
