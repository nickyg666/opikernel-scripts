#!/usr/bin/env bash
# Quarantine (never delete) the module dirs on the card that can never be the
# boot release of the shipped Image, plus the .bak-* module copies.
#
# Why this matters: kmod resolves a module by UNAME, not by Image. The Image
# banner is the only authority for which lib/modules/<rel> is live. A dir whose
# name is one plausible uname away from the real one is a live landmine: if uname
# ever equals it, the kernel silently loads THAT dir instead.
#
# Moved to /mnt/sd/lib/modules/.quarantine-<ts>/ and left in place. Nothing is
# removed from the card, so this is reversible with one mv.
set -uo pipefail
TAB=${TAB:-tab@192.168.0.149}
TABPW=${TABPW:-1}
# NO DEFAULT, ON PURPOSE. A default here is how a 465G number met a 32G card and
# looked like a pass. 974848000 = 465G production, 62333952 = 32G staging.
# The two cards are clones (same UUID AND same PARTUUID) so size is the only
# identity left -- and it must come from the operator, every run.
EXPECT_SIZE=${EXPECT_SIZE:-}
M=/mnt/sd
TS=$(date +%Y%m%d-%H%M%S)

# Substitute with sed on explicit tokens. A QUOTED heredoc ('EOS') does no
# expansion, so writing `EXP=$EXP` inside it leaves the remote assigning its own
# unset value -> empty string, and the identity guard then compares "" to "" and
# PASSES. That is the worst possible failure for this script: it would let any
# card through. Never self-assign a host var into a quoted heredoc.
body=$(cat <<'EOS'
M=@MOUNTPOINT@
EXP=@EXPSIZE@
TS=@TS@
[ -n "$EXP" ] || { echo "EXPECT_SIZE required (no default on purpose): 974848000=465G, 62333952=32G"; exit 1; }
# Find the card by IDENTITY, not by name. sda/sdb shuffle between sessions: the
# 465G left the reader and the 32G took its name. A hardcoded /dev/sda here means
# either CARD_ID (fails safe) or, if sda is absent, an empty compare.
CARD=""
for d in /sys/block/sd*; do
  [ -e "$d/size" ] || continue
  if [ "$(cat $d/size 2>/dev/null)" = "$EXP" ]; then CARD=${d#/sys/block/}; break; fi
done
[ -n "$CARD" ] || { echo "CARD_ID no reader device has size=$EXP -- REFUSING"; exit 1; }
id=$(cat /sys/block/$CARD/size)
PART=$(ls /sys/block/$CARD/$CARD/ 2>/dev/null >/dev/null; lsblk -no NAME 2>/dev/null | grep -m1 "^${CARD}[0-9]" || echo "${CARD}1")
echo "CARD_DEV=$CARD part=$PART size=$id"
mountpoint -q $M || mount -o rw /dev/$PART $M
mountpoint -q $M || { echo "MOUNT_FAIL"; exit 1; }
# A read-only mountpoint is NOT a mountpoint problem -- it silently turns every
# `mv` below into a no-op that still increments the counter, so the script
# reports a prune that never happened. Verify rw by writing, not by parsing
# findmnt (PA: "source write-protected" is a misleading errno string).
t=$M/.quar-wtest.$$
if ! ( echo ok > "$t" ) 2>/dev/null; then
  echo "MOUNT_RO $M is not writable (tried to write $t) -- REFUSING, nothing was moved"; exit 1
fi
rm -f "$t"
REL=$(strings -a $M/boot/mainline/Image | grep -m1 -o 'Linux version 7[^ ]*' | cut -d' ' -f3)
[ -n "$REL" ] || { echo "NO_RELEASE (card unreadable?) -- REFUSING"; exit 1; }
LIVE=$M/lib/modules/$REL
echo "identity=$id live=$REL"
Q=$M/lib/modules/.quarantine-$TS
mkdir -p $Q || { echo "MKDIR_FAIL (read-only?)"; exit 1; }
moved=0
for d in $M/lib/modules/*/; do
  b=$(basename "$d")
  case "$b" in
    7.3.0-rc2*|6.*)
      if [ "$b" != "$REL" ]; then
        mv "$d" "$Q/" 2>/dev/null && { echo "QUARANTINED_DIR $b ($(du -sh "$d" 2>/dev/null | cut -f1))"; moved=$((moved+1)); }
      fi
      ;;
  esac
done
bakmoved=0
for b in $(find $M/lib/modules -maxdepth 2 -name '*.bak*' 2>/dev/null); do
  t="$Q/$(echo "${b#$M/lib/modules/}" | tr / _)"
  mv "$b" "$t" 2>/dev/null && bakmoved=$((bakmoved+1))
done
echo "dirs_moved=$moved baks_moved=$bakmoved"
echo "--- live dir intact ---"
ls -1 $LIVE/*.ko 2>/dev/null | wc -l
echo "--- remaining kver dirs ---"
ls -1d $M/lib/modules/*/ 2>/dev/null | grep -v quarantine
echo "--- du ---"
du -sh $M/lib/modules
id2=$(cat /sys/block/$CARD/size 2>/dev/null)
[ "$id2" = "$id" ] && echo "identity_stable=$id2" || echo "CARD_ID_CHANGED $id -> $id2"
EOS
)
b64=$(printf '%s' "$body" \
  | sed -e "s|@MOUNTPOINT@|$M|g" -e "s|@EXPSIZE@|$EXPECT_SIZE|g" -e "s|@TS@|$TS|g" \
  | base64 -w0)
sshpass -p "$TABPW" ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 "$TAB" \
  "echo '$TABPW' | sudo -S bash -c 'echo $b64 | base64 -d | bash -s'"
rcremote=$?

# The remote refuses by exit status. Losing it here means a REFUSED run still
# exits 0 and still poisons the host table -- the gate-that-lies class, twice.
echo "remote_rc=$rcremote"
if [ "$rcremote" != "0" ]; then
  echo "CARD_STEP_REFUSED (rc=$rcremote) -- host dep table NOT poisoned, nothing pruned"
  exit "$rcremote"
fi

echo
echo "== poison the stale host dep table =="
GEN=/home/host/opikernel/stage/7.3-stage/lib/modules/modules.dep.generated
if [ -f "$GEN" ]; then
  cp -a "$GEN" "$GEN.POISON-$(date +%Y%m%d-%H%M%S)"
  cat > "$GEN" <<'EOF'
# POISONED 2026-09-30. DO NOT SHIP. DO NOT REGENERATE WITHOUT A REAL depmod RUN.
# This file predates the drm_kms_helper fix and lists only 4 powervr prereqs;
# the card's correct table lists 5. Shipping it reverts
#   drm_shmem_helper.ko: drm_kms_helper.ko
# and silently breaks the whole GPU chain. The card's own modules.dep is the
# authority. See kernel/references/depmod-swallows-prereqs.md
EOF
  echo "POISONED $GEN (backup alongside)"
fi
