#!/usr/bin/env bash
# card-identity-from-serial.sh — which physical SD card is the board running?
#
# WHY THIS EXISTS (2026-09-30): the two lab cards are CLONES of each other at
# the filesystem level. Both answer root=PARTUUID=486ea4ae-01, both carry rootfs
# UUID 442af407. Nothing on a card can tell you which card it is, so every
# "swap the card" argument in the room was unfalsifiable and kept ping-ponging.
#
# The discriminator is the MMC CID/eMMC name the kernel prints, which lives in
# silicon and cannot be cloned:
#     mmcblk1: mmc1:aaaa SL32G 29.7 GiB     <- 32GB staging card
#     mmcblk1: mmc1:aaaa LX512 465G         <- 465GB production card
# RANK: mmcblk1 model string OUTRANKS UUID, PARTUUID, LABEL and hostname.
#
# Read-only. Touches nothing, powers nothing, never writes to a card.
#
# USAGE
#   card-identity-from-serial.sh [LOG]     # default: the room's single live log
#   exits 0 = identified, 3 = ambiguous/stale, 4 = no evidence found
set -uo pipefail

LOG="${1:-/home/host/opikernel/pvrgl-work/sercap_room_live.log}"
[ -r "$LOG" ] || { echo "NO_LOG $LOG"; exit 4; }

# Segment the log on kernel-version banners so we report the CURRENT boot, not
# a count over all history. A stale early boot must never answer this question.
BOOT_BANNER='Linux version [0-9]'

# Most recent boot = text after the last banner occurrence.
LAST_BOOT=$(awk -v pat="$BOOT_BANNER" '
  $0 ~ pat { buf = "" }
  { buf = buf "\n" $0 }
  END { print buf }
' "$LOG")

KVER=$(printf '%s\n' "$LAST_BOOT" | grep -aoE 'Linux version [0-9][^ ]*' | head -1 | awk '{print $3}')
KNO=$(printf '%s\n' "$LAST_BOOT" | grep -aoE '#[0-9]+' | head -1)
CARD=$(printf '%s\n' "$LAST_BOOT" | grep -aoE 'mmcblk1: mmc1:[0-9a-f]+ [^ ]+ [0-9.]+ ?GiB' | head -1)
HOSTNAME=$(printf '%s\n' "$LAST_BOOT" | grep -aoE "hostname=[a-z0-9]+" | head -1 | cut -d= -f2)
LOGIN=$(printf '%s\n' "$LAST_BOOT" | grep -aqc 'login:' && echo yes || echo no)

if [ -z "$CARD" ]; then
  echo "NO_MMC_EVIDENCE rc=4  (log has no mmcblk1 model line in the last boot)"
  echo "  -> do NOT guess. An absent line is missing evidence, not the 32G."
  exit 4
fi

SIZE=$(printf '%s' "$CARD" | awk '{print $(NF-1)" "$(NF-0)}')
case "$CARD" in
  *LX512*) NAME=465G-production-card ;;
  *SL32G*) NAME=32G-staging-card ;;
  *)       NAME=UNKNOWN-CARD ;;
esac

echo "CARD_IN_BOARD  $NAME"
echo "  mmc_line : $CARD"
echo "  kernel   : ${KVER:-?} ${KNO:-?}"
echo "  hostname : ${HOSTNAME:-?}   login_reached: $LOGIN"
echo "  log      : $LOG"

if [ "$NAME" = UNKNOWN-CARD ]; then
  echo "VERDICT UNKNOWN — add this model string to the case list before trusting it."
  exit 3
fi
echo "VERDICT IDENTIFIED — mmc model outranks UUID/PARTUUID/hostname. Exit 0."
