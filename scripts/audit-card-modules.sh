#!/usr/bin/env bash
# GATE 4: does the CARD actually satisfy the boot, and is the host's copy of the
# dep table safe to ship?
#
# Gate 3 (audit-stage-vs-tree.py) proves stage/ matches the build tree. It says
# nothing about the card. This is the check that actually blocks a boot:
#
#   RELEASE_MISSING   the Image banner's uname -r has no lib/modules/<rel> dir
#   KO_MISSING        a .ko the card's modules.dep / modules-load.d names is absent
#   DEP_DANGLING      a prereq in modules.dep resolves to no file on the card
#                     (depmod DROPS these silently, so the table reads
#                      self-consistent while the whole chain fails to load)
#   LOAD_STALE        modules-load.d names a module absent from the boot dir
#   STALE_GENERATED   host modules.dep.generated disagrees with the card table
#                     (shipping it reverts a fix)
#
# Card identity is read from the reader in THIS session, before and after, and
# must be constant. Never trust a card size copied from a note or a script.
#
# NOTE: every finding is appended to a file, never set from inside a pipeline.
# `while read` in a pipe is a SUBSHELL: `fail=1` there cannot reach the parent,
# which makes a FAIL print GATE4_CLEAN. That is the false-negative this gate
# exists to prevent; do not "simplify" it back into a pipe.
set -uo pipefail

TAB=${TAB:-tab@192.168.0.149}
TABPW=${TABPW:-1}
EXPECT_SIZE=${EXPECT_SIZE:-}   # NO DEFAULT: 974848000=465G production, 62333952=32G staging.
                               # Clone cards share UUID AND PARTUUID, so size is all
                               # that is left, and a stale default reads as a PASS.
M=/mnt/sd
F=$(mktemp /tmp/gate4.XXXXXX)
fail=0
note() { printf '%s\n' "$*" | tee -a "$F"; }
bad()  { printf ' ! %s\n' "$*" | tee -a "$F"; fail=1; }

run() {
  # The remote body is base64-piped, never single-quoted inline: nesting quotes
  # inside the ssh command silently mangles the remote script (it cost me a
  # wrong REL="Linux" and two false gate findings).
  b64=$(printf '%s' "$1" | base64 -w0)
  sshpass -p "$TABPW" ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$TAB" \
    "echo '$TABPW' | sudo -S bash -c 'echo $b64 | base64 -d | bash -s'" 2>/dev/null
}
runc() {   # run, keep the answer on one line only
  run "$1" | tr -d '\r' | tail -1
}
# `mountpoint -q` and `test -f` are SILENT and signal via exit status only, so
# their output can never be grepped. Wrap them so the answer is a real string.
yorn() { run "$1" >/dev/null 2>&1 && echo yes || echo no; }

note "== card identity =="
if [ -z "$EXPECT_SIZE" ]; then
  bad "EXPECT_SIZE unset (no default on purpose) - 974848000=465G production, 62333952=32G staging"
  echo; echo "GATE4_FAIL"; exit 1
fi
# Resolve the card by size, never by name: the 465G left the reader and the 32G
# took the name sda/sdb, so a hardcoded sda silently audits whichever card is
# absent (empty size compare) or the wrong one.
CARD=""
for d in /sys/block/sd*; do
  [ -e "$d/size" ] || continue
  ids=$(cat "$d/size" 2>/dev/null)
  [ "$ids" = "$EXPECT_SIZE" ] && { CARD=${d#/sys/block/}; break; }
done
if [ -z "$CARD" ]; then
  bad "CARD_ID no reader device has size=$EXPECT_SIZE - WRONG CARD IN READER (or none)"
  echo; echo "GATE4_FAIL"; exit 1
fi
note "  /sys/block/$CARD/size = $EXPECT_SIZE (matched by size, not by name)"
PART=$(runc "lsblk -no NAME | grep -m1 '^${CARD}[0-9]'")
[ -n "$PART" ] || PART="${CARD}1"
note "  card partition = $PART"

note "== mount =="
if [ "$(yorn "mountpoint -q $M")" != "yes" ]; then
  run "mount /dev/$PART $M" >/dev/null
  sleep 1
fi
if [ "$(yorn "mountpoint -q $M")" != "yes" ]; then bad "MOUNT $M not mounted; audit aborted"; echo; echo "GATE4_FAIL"; exit 1; fi
note "  $M mounted"

REL=$(runc "strings -a $M/boot/mainline/Image | grep -m1 -o 'Linux version 7[^ ]*' | cut -d' ' -f3")
note "== boot release =="
note "  Image banner uname -r = $REL"
R="$M/lib/modules/$REL"
# Test existence ON THE REMOTE. A local `test -d` answers about the HOST's
# /mnt/sd, which does not exist -> permanent false RELEASE_MISSING.
if [ "$(yorn "test -d $R")" != "yes" ]; then
  bad "RELEASE_MISSING no $M/lib/modules/$REL (Image booted, modules dir absent -> zero modules load)"
  R=""
fi

if [ -n "$R" ]; then
  note "== shipped .ko =="
  run "ls -1 $R/*.ko 2>/dev/null" | while read -r f; do [ -n "$f" ] && note "  $(basename "$f")"; done
  n=$(runc "ls -1 $R/*.ko 2>/dev/null | wc -l")
  note "  count=$n"
  [ "${n:-0}" -gt 0 ] || bad "KO_NONE no .ko in $R"

  note "== vermagic of every shipped .ko =="
  badvm=$(run "for f in $R/*.ko; do v=\$(modinfo -F vermagic \$f 2>/dev/null | cut -d' ' -f1); [ \"\$v\" = '$REL' ] || echo \"\$(basename \$f) vm=\$v\"; done")
  if [ -n "$badvm" ]; then
    printf '%s\n' "$badvm" > "$F.bvm"
    while read -r l; do [ -n "$l" ] && bad "VERMAGIC $l (expected $REL)"; done < "$F.bvm"
  else
    note "  all ${n} carry $REL"
  fi

  note "== DEP_DANGLING: every prereq in modules.dep must be a real file =="
  dang=$(run "awk -F': ' '/\\.ko:/{split(\$2,a,\" \"); for(i in a) if(a[i]!=\"\") print \$1\" \"a[i]}' $R/modules.dep 2>/dev/null | while read k p; do [ -f $R/\$p ] || echo \"\$k needs \$p\"; done")
  if [ -n "$dang" ]; then
    printf '%s\n' "$dang" > "$F.dang"
    while read -r l; do [ -n "$l" ] && bad "DEP_DANGLING $l"; done < "$F.dang"
  else
    note "  none"
  fi

  note "== LOAD_STALE: modules-load.d vs shipped set =="
  conf=$(run "cat $M/etc/modules-load.d/opiz3w.conf 2>/dev/null")
  printf '%s\n' "$conf" > "$F.conf"
  while read -r m; do
    [ -z "${m// /}" ] && continue
    if [ "$(yorn "test -f $R/$m.ko")" != "yes" ]; then
      bad "LOAD_STALE $m absent from $REL"
    fi
  done < "$F.conf"
fi

note "== STALE_GENERATED: host modules.dep.generated must not contradict the card =="
GEN=/home/host/opikernel/stage/7.3-stage/lib/modules/modules.dep.generated
if [ -f "$GEN" ]; then
  cardpow=$(runc "grep -h '^powervr.ko:' $R/modules.dep 2>/dev/null" | sed 's/^powervr.ko: *//' | tr ' ' '\n' | grep -c '\.ko$')
  genpow=$(grep '^powervr.ko:' "$GEN" | sed 's/^powervr.ko: *//' | tr ' ' '\n' | grep -c .)
  note "  card powervr prereqs=${cardpow:-0}  generated prereqs=${genpow:-0}"
  if [ "${cardpow:-0}" != "${genpow:-0}" ]; then
    bad "STALE_GENERATED $GEN has ${genpow:-0} powervr prereqs, card has ${cardpow:-0} - do NOT ship it, use the card's modules.dep"
  fi
else
  note "  absent"
fi

note "== identity AFTER (must be unchanged) =="
id2=$(runc "cat /sys/block/$CARD/size")
note "  $id2"
[ "$id2" = "$EXPECT_SIZE" ] || bad "CARD_ID_CHANGED $EXPECT_SIZE -> $id2 during the audit; results are untrustworthy"

rm -f "$F" "$F.bvm" "$F.dang" "$F.conf"
echo
if [ "$fail" = "1" ]; then echo "GATE4_FAIL"; exit 1; fi
echo "GATE4_CLEAN  card=$EXPECT_SIZE  release=$REL"
