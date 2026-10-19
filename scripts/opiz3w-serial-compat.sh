#!/bin/bash
# opiz3w-serial-compat.sh — reconcile the stable board-console path so that the
# 400+ legacy scripts that hardcode /dev/ttyACM0 keep working after a Picoprobe
# re-enumeration (unbind/bind, replug, hub reset -> ttyACM1/ttyACM2/...).
#
# WHY THIS EXISTS: /dev/opiz3w-serial (udev, 99-opiz3w-serial.rules) is the
# canonical name, but the long tail of historical pipelines in
# /home/host/opikernel hardcodes /dev/ttyACM0. When the probe re-enumerates,
# those scripts silently open nothing and the board "looks dead". Patching 421
# files is not a fix (new files re-introduce the bug); this reconcile is.
#
# IDEMPOTENT. Safe to run every minute from cron, or from a udev add event.
# It NEVER opens the port, so it cannot disturb the single-owner capture.
#
# RULES:
#   real node == /dev/ttyACM0        -> guarantee no stale symlink is left at other names
#   real node != /dev/ttyACM0        -> ensure /dev/ttyACM0 is a symlink to it
#   probe absent                     -> drop /dev/ttyACM0 ONLY if it is a symlink
#
# Usage: opiz3w-serial-compat.sh [--quiet]

STABLE="/dev/opiz3w-serial"
COMPAT="/dev/ttyACM0"
QUIET=0
[ "$1" = "--quiet" ] && QUIET=1

log() { [ "$QUIET" = 1 ] || echo "$@"; }

# --- resolve the real character device -------------------------------------
REAL=""
if [ -L "$STABLE" ]; then
    REAL="$(readlink -f "$STABLE" 2>/dev/null)"
fi
# fall back to scanning for the Picoprobe by USB id if the symlink is missing
if [ -z "$REAL" ] || [ ! -c "$REAL" ]; then
    REAL=""
    for n in /dev/ttyACM*; do
        [ -c "$n" ] || continue
        # only accept nodes that came from the pico (2e8a:000a)
        d="$(basename "$n")"
        if udevadm info -q property -n "$n" 2>/dev/null | grep -qx 'ID_VENDOR_ID=2e8a'; then
            REAL="$n"
            break
        fi
    done
fi

# --- reconcile --------------------------------------------------------------
if [ -z "$REAL" ]; then
    if [ -L "$COMPAT" ]; then
        rm -f "$COMPAT" && log "probe absent -> removed stale compat symlink $COMPAT"
    else
        log "probe absent; nothing to do"
    fi
    exit 0
fi

if [ "$REAL" = "$COMPAT" ]; then
    log "real node is already $COMPAT — no compat alias needed"
    exit 0
fi

CUR="$(readlink "$COMPAT" 2>/dev/null || true)"
WANT="$(basename "$REAL")"
if [ "$CUR" = "$WANT" ] && [ -L "$COMPAT" ]; then
    log "compat alias already correct: $COMPAT -> $WANT"
    exit 0
fi

if [ -e "$COMPAT" ] && [ ! -L "$COMPAT" ]; then
    # a real character device is sitting on ttyACM0 that is NOT the probe —
    # never clobber it; report loudly instead.
    echo "WARN: $COMPAT is a real device and not the Picoprobe ($REAL); leaving it alone" >&2
    exit 1
fi

ln -sfn "$WANT" "$COMPAT" && log "compat alias set: $COMPAT -> $WANT (stable: $STABLE)"
exit 0
