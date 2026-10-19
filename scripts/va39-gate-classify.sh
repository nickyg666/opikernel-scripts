#!/bin/bash
# va39-gate-classify.sh — deterministic boot-gate classifier. NO LLM judgement.
#
# WHY: the va39-gate-watch cron is an LLM reporter, and it twice posted a verdict the
# evidence did not support ("GATE: Unknown" / "GATE: NO_MATCH — No Linux version")
# because it was pointed at a log path that no longer existed and had to guess. A gate
# verdict that depends on prose interpretation is worthless. This script reads the
# bytes and prints exactly one line; the reporter's only job is to post it verbatim.
#
# Usage:  va39-gate-classify.sh            print the verdict + evidence clause
#         va39-gate-classify.sh --changed  print ONLY if it differs from last verdict
#         va39-gate-classify.sh --post     post via gc-say when changed
#
# Exit:   0 verdict printed | 10 unchanged (with --changed/--post) | 1 no evidence

set -uo pipefail
PV=/home/host/opikernel/pvrgl-work
STATE="$PV/.va39-gate-verdict"
MODE="${1:-}"

# Ordered candidate list. First existing + non-empty + newest wins, EXCEPT the
# authoritative file which always wins if it exists at all.
AUTHORITATIVE="$PV/sercap_manual_earlycon.log"

pick_log() {
    if [ -s "$AUTHORITATIVE" ]; then echo "$AUTHORITATIVE"; return; fi
    local best="" best_mt=0 f mt
    for f in "$PV"/sercap_*.log; do
        [ -s "$f" ] || continue
        case "$f" in *.out) continue;; esac
        mt=$(stat -c %Y "$f" 2>/dev/null || echo 0)
        if [ "$mt" -gt "$best_mt" ]; then best="$f"; best_mt=$mt; fi
    done
    echo "$best"
}

LOG="$(pick_log)"
if [ -z "$LOG" ] || [ ! -s "$LOG" ]; then
    echo "GATE: NO_EVIDENCE — no non-empty sercap_*.log in $PV"
    exit 1
fi

AGE=$(( $(date +%s) - $(stat -c %Y "$LOG") ))
AGE_MIN=$(( AGE / 60 ))
STALE=""
[ "$AGE_MIN" -gt 45 ] && STALE=" (log ${AGE_MIN}m old)"

# NOTE: the capture log contains NUL bytes (U-Boot/ATF padding), so grep treats it as
# binary and silently prints nothing / reports "binary file matches". -a is mandatory
# here — without it the classifier read no evidence and reported the wrong verdict,
# which is exactly the failure mode this script exists to kill.
has() { grep -qaF -- "$1" "$LOG" 2>/dev/null; }
grab() { grep -am1 -o "$1" "$LOG" 2>/dev/null | tr -d '\000' | cut -c1-140; }

# --- classify (order matters: a crash verdict outranks a booting verdict) ----
if has 'sunxi_bsp_pinctrl_init_with_variant'; then
    PC=$(grab 'pc : sunxi_bsp_pinctrl_init_with_variant+0x[0-9a-f]*')
    VERDICT="BLOCKER_PINCTRL_PROBE_OOPS"
    EVID="kernel alive, root never mounts; ${PC:-Oops at sunxi_bsp_pinctrl_init_with_variant}"
elif has 'Kernel panic'; then
    VERDICT="FAILED_KERNEL_PANIC"
    EVID="$(grab 'Kernel panic.*')"
elif has 'Linux version'; then
    if has 'Waiting for root device'; then
        VERDICT="BOOTING_ROOT_NOT_MOUNTED"
        EVID="$(grab 'Waiting for root device.*')"
    else
        VERDICT="KERNEL_ALIVE_NO_ROOT_WAIT_YET"
        EVID="$(grab 'Linux version.*')"
    fi
else
    VERDICT="NO_KERNEL_OUTPUT"
    EVID="no 'Linux version' in $(basename "$LOG") — console never opened (missing earlycon?)"
fi

# Dedupe KEY deliberately EXCLUDES the log-age suffix. Including it made every tick a
# "changed" verdict ("…(log 48m old)" -> "…(log 50m old)") and the room got the same GATE
# line re-posted every 4 minutes. Key = what actually changed: verdict + evidence + log.
BASE="$(basename "$LOG")"
KEY="${VERDICT}|${EVID}|${BASE}"
LINE="GATE: ${VERDICT} — ${EVID}${STALE}  [${BASE}]"

PREV="$(cat "$STATE" 2>/dev/null || true)"
case "$MODE" in
    --changed|--post)
        if [ "$KEY" = "$PREV" ]; then
            exit 10
        fi
        printf '%s\n' "$KEY" > "$STATE"
        echo "$LINE"
        if [ "$MODE" = "--post" ]; then
            /home/host/bin/gc-say "$LINE" >/dev/null 2>&1 || true
        fi
        ;;
    *)
        printf '%s\n' "$LINE"
        ;;
esac
exit 0
