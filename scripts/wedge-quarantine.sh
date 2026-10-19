#!/bin/bash
# wedge-quarantine.sh — the ONE fail-closed path to the dead-lane (quarantine) list
# (PA, 2026-09-20).  Callers: scripts/kernel-room-nudge.sh, scripts/group-orchestrator.sh.
#
# WHY THIS EXISTS
#   scripts/lane-wedge-check.py is the one PREDICATE; this is the one CALLER CONTRACT.
#   Twice today a caller turned an UNKNOWN verdict into "healthy":
#     * kernel-room-nudge.sh had an inline copy of the predicate query; its uncoalesced
#       sum(lastError LIKE '%reaped%') returned NULL, raised TypeError, and under
#       `set -e` killed the whole tick silently (20:38, 20:40: no nudge at all).
#     * group-orchestrator.sh line 404 piped the tool through `|| true`, so rc=2 (DB
#       error / DEGRADED) became an EMPTY list -> every wedged lane was mentioned again
#       (digests 20:37:32 / 20:38:37 / 20:39:41).
#   rc alone is not proof either: a predicate that cannot even be parsed exits 1 with
#   empty output, byte-identical to a healthy "no wedged lanes". So a clean rc is
#   trusted ONLY when the tool also parses.
#
# CONTRACT
#   stdout : the lane list ("name<TAB>why", or names only) — possibly REUSED from the
#            last known-good file. Never diagnostics: callers treat stdout as lanes.
#   stderr : WARN / DEGRADED lines for the caller's log.
#   rc     : ALWAYS 0. The UNKNOWN case is handled HERE, so no caller can `|| true`
#            its way into reading DEGRADED as healthy.
#
# ENV
#   WEDGE_ROOM / ROOM_ID   room id (required)
#   WEDGE_DB               sqlite path        (default the web-ui group-chat DB)
#   WEDGE_TOOL             predicate path     (overridable to test the broken path)
#   WEDGE_MODE             --all | --names-only   (default --all)
#   WEDGE_LAST             last-known-good file (default state/wedge-last.txt)
#   WEDGE_TIMEOUT          seconds            (default 10)
#   WEDGE_WINDOW_MIN/WEDGE_MIN_REAPS/WEDGE_PILE  passed through to the predicate
set -uo pipefail

ROOM="${WEDGE_ROOM:-${ROOM_ID:-}}"
DB="${WEDGE_DB:-/home/host/.hermes-web-ui/hermes-web-ui.db}"
TOOL="${WEDGE_TOOL:-/home/host/opikernel/scripts/lane-wedge-check.py}"
MODE="${WEDGE_MODE:---all}"
LAST="${WEDGE_LAST:-/home/host/opikernel/state/wedge-last.txt}"

if [ -z "$ROOM" ]; then
  echo "[$(date -Is)] WARN: wedge-quarantine called with no room (UNKNOWN) — empty list" >&2
  exit 0
fi
mkdir -p "$(dirname "$LAST")" 2>/dev/null || true

set +e
ERRLOG="${WEDGE_ERRLOG:-$(mktemp "${TMPDIR:-/home/host/opikernel/state}/wedge-err.XXXXXX")}"
OUT=$(WEDGE_DB="$DB" \
      WEDGE_WINDOW_MIN="${WEDGE_WINDOW_MIN:-180}" \
      WEDGE_MIN_REAPS="${WEDGE_MIN_REAPS:-4}" \
      WEDGE_PILE="${WEDGE_PILE:-40}" \
      timeout "${WEDGE_TIMEOUT:-10}" python3 "$TOOL" --room "$ROOM" "$MODE" 2>"$ERRLOG")
RC=$?
set -e

TOOLOK=0
if python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$TOOL" 2>/dev/null; then
  TOOLOK=1
fi

# The predicate's OWN stderr is the only place the DEGRADED reason (which name owns
# how many LIVE agentIds) and its retired-id NOTEs are written. Swallowing it here
# would leave the log with a bare rc and no cause.
if [ -s "$ERRLOG" ]; then cat "$ERRLOG" >&2; fi
rm -f "$ERRLOG" 2>/dev/null || true

if [ "$RC" -le 1 ] && [ "$TOOLOK" = "1" ]; then
  printf '%s\n' "$OUT" | awk 'NF' > "$LAST"
  awk 'NF' "$LAST"
  exit 0
fi

echo "[$(date -Is)] WARN: wedge predicate DEGRADED rc=$RC toolok=$TOOLOK (UNKNOWN, not healthy) — reusing $LAST" >&2
if [ -s "$LAST" ]; then
  awk 'NF' "$LAST"
else
  echo "[$(date -Is)] WARN: no known-good wedge list yet — quarantine EMPTY this tick" >&2
fi
exit 0
