#!/bin/bash
# wedge-twin-guard-selftest.sh — proves the dead-lane predicate's twin guard and the
# fail-closed caller contract in BOTH directions (PA, 2026-09-20).
#
# A guard that only ever fires is as broken as the one that never fires, and a guard
# that cannot tell a LIVE twin from a RETIRED ghost id freezes the whip forever:
#   * HARD: one name, >1 LIVE roster agentId in ONE room -> rc=2 DEGRADED, stdout
#     EMPTY (stdout is lanes; a diagnostic there would be read as a lane name)
#   * SOFT: same name + RETIRED agentIds (agent re-created) -> NOTE only, normal rc,
#     lane list unchanged — blocking here would pin the breaker to its last list
#   * same name in a DIFFERENT room -> neither class (gc_room_agents is per-room)
#   * predicate broken/unparseable -> caller hands back the LAST KNOWN-GOOD list,
#     never an empty one (the empty-list path is what re-armed the whip 20:37-20:39)
# Everything runs against synthetic DBs; the live DB is only READ.
set -uo pipefail
cd /home/host/opikernel
TOOL=/home/host/opikernel/scripts/lane-wedge-check.py
HELP=/home/host/opikernel/scripts/wedge-quarantine.sh
LIVE_DB=/home/host/.hermes-web-ui/hermes-web-ui.db
TMP=$(mktemp -d /home/host/opikernel/state/twin-selftest.XXXXXX)
FAIL=0
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; FAIL=$((FAIL+1)); }
chk()  { if [ "$2" = "$3" ]; then ok "$1 ($2)"; else bad "$1: got '$2' want '$3'"; fi; }

python3 - <<PY
import sqlite3, time
now = int(time.time()*1000)
def mk(path, rows, roster):
    con = sqlite3.connect(path)
    con.executescript("""
      CREATE TABLE gc_room_agents(id TEXT PRIMARY KEY, roomId TEXT, agentId TEXT,
                                  name TEXT, removedAt INTEGER DEFAULT 0);
      CREATE TABLE gc_execution_queue(id TEXT PRIMARY KEY, roomId TEXT, messageId TEXT,
             targetAgentId TEXT, targetAgentName TEXT, status TEXT, createdAt INTEGER,
             startedAt INTEGER, finishedAt INTEGER, lastError TEXT);
    """)
    for r in rows:
        con.execute("INSERT INTO gc_execution_queue VALUES(?,?,?,?,?,?,?,?,?,?)", r)
    for r in roster:
        con.execute("INSERT INTO gc_room_agents VALUES(?,?,?,?,?)", r)
    con.commit()

class B(object):
    def __init__(self): self.rows = []; self.n = 0
    def q(self, room, name, aid, status, created, last=None, finished=None):
        self.n += 1
        self.rows.append((str(self.n), room, "m%d" % self.n, aid, name, status,
                          created, None, finished, last))

# --- db_ok: one healthy lane + one clearly dead lane, NO ambiguity -------------
b = B()
for k in range(40): b.q("roomA", "deadlane", "a1", "queued", now - 5*60000)
for k in range(3):  b.q("roomA", "solo", "a2", "queued", now - 5*60000)
b.q("roomA", "solo", "a2", "completed", now - 60000, finished=now - 1000)
b.q("roomB", "solo", "a9", "completed", now - 60000, finished=now - 1000)  # other room
mk("$TMP/ok.db", b.rows, [("r1", "roomA", "a1", "deadlane", 0),
                          ("r2", "roomA", "a2", "solo", 0),
                          ("r3", "roomB", "a9", "solo", 0)])

# --- db_soft: one LIVE id + RETIRED ids for the same name -> NOTE, not DEGRADED -
b = B()
for k in range(40): b.q("roomA", "deadlane", "a1", "queued", now - 5*60000)
b.q("roomA", "solo", "a2", "completed", now - 60000, finished=now - 1000)
b.q("roomA", "solo", "a8", "failed", now - 900000, last="agent re-created")   # ghost
b.q("roomA", "solo", "a8", "failed", now - 899000, last="agent re-created")
mk("$TMP/soft.db", b.rows, [("r1", "roomA", "a1", "deadlane", 0),
                            ("r2", "roomA", "a2", "solo", 0)])  # a8 NOT on the roster

# --- db_twin: name 'twin' owns TWO LIVE roster ids inside roomA ----------------
#     b1 is stuck (40 queued, 0 completions); b2 completes right now -> the
#     name-keyed stats read done=1, i.e. the wedge is MASKED.
b = B()
for k in range(40): b.q("roomA", "twin", "b1", "queued", now - 5*60000)
b.q("roomA", "twin", "b2", "completed", now - 60000, finished=now - 1000)
mk("$TMP/twin.db", b.rows, [("t1", "roomA", "b1", "twin", 0),
                            ("t2", "roomA", "b2", "twin", 0)])
print("synthetic DBs in $TMP: ok.db soft.db twin.db")
PY

echo "--- A: no ambiguity -> normal verdict, list unchanged"
OUT=$(WEDGE_DB="$TMP/ok.db" python3 "$TOOL" --room roomA --all 2>"$TMP/a.err"); RC=$?
echo "      rc=$RC out='$OUT' err='$(cat "$TMP/a.err")'"
chk "A rc" "$RC" "0"
chk "A lane list" "$(printf '%s' "$OUT" | cut -f1 | tr '\n' ',')" "deadlane,"
chk "A no DEGRADED" "$(grep -c DEGRADED "$TMP/a.err")" "0"

echo "--- B: >1 LIVE roster agentId for one name -> rc=2, DEGRADED, stdout CLEAN"
OUT=$(WEDGE_DB="$TMP/twin.db" python3 "$TOOL" --room roomA --all 2>"$TMP/b.err"); RC=$?
echo "      rc=$RC out='$OUT' err='$(head -1 "$TMP/b.err")'"
chk "B rc" "$RC" "2"
chk "B stdout empty (a diagnostic must never look like a lane name)" "$(printf '%s' "$OUT" | wc -c)" "0"
chk "B DEGRADED said out loud" "$(grep -c 'DEGRADED twin identity' "$TMP/b.err")" "1"

echo "--- B2: RETIRED ghost ids only -> NOTE, normal verdict (must NOT freeze the whip)"
OUT=$(WEDGE_DB="$TMP/soft.db" python3 "$TOOL" --room roomA --all 2>"$TMP/b2.err"); RC=$?
echo "      rc=$RC out='$OUT' err='$(head -1 "$TMP/b2.err")'"
chk "B2 rc" "$RC" "0"
chk "B2 lane list intact" "$(printf '%s' "$OUT" | cut -f1 | tr '\n' ',')" "deadlane,"
chk "B2 no DEGRADED" "$(grep -c DEGRADED "$TMP/b2.err")" "0"
chk "B2 NOTE printed" "$(grep -c 'retired agentId' "$TMP/b2.err")" "1"

echo "--- C: caller contract, healthy predicate -> stdout = lanes, state written"
rm -f "$TMP/last.txt"
OUT=$(WEDGE_DB="$TMP/ok.db" WEDGE_ROOM=roomA WEDGE_TOOL="$TOOL" WEDGE_LAST="$TMP/last.txt" \
      WEDGE_MODE=--all bash "$HELP" 2>"$TMP/c.err"); RC=$?
echo "      rc=$RC out='$OUT' persisted='$(cat "$TMP/last.txt" 2>/dev/null)'"
chk "C rc" "$RC" "0"
chk "C out" "$(printf '%s' "$OUT" | cut -f1)" "deadlane"
chk "C state persisted" "$(cut -f1 "$TMP/last.txt")" "deadlane"

echo "--- D: predicate BROKEN -> caller FAILS CLOSED on last known-good, not empty"
printf 'deadlane\t12 mentions undrained, 0 completed since 19:00\n' > "$TMP/last.txt"
printf 'def broken(:\n' > "$TMP/broken.py"
OUT=$(WEDGE_DB="$TMP/ok.db" WEDGE_ROOM=roomA WEDGE_TOOL="$TMP/broken.py" WEDGE_LAST="$TMP/last.txt" \
      WEDGE_MODE=--all bash "$HELP" 2>"$TMP/d.err"); RC=$?
echo "      rc=$RC out='$OUT' err='$(head -1 "$TMP/d.err")'"
chk "D rc (never fails the caller)" "$RC" "0"
chk "D reused last known-good" "$(printf '%s' "$OUT" | cut -f1)" "deadlane"
chk "D WARN DEGRADED" "$(grep -c 'DEGRADED' "$TMP/d.err")" "1"

echo "--- E: live DB -> helper identical to the bare predicate; NO hard twin"
ROOM=mti5ax1clq0zlx
A=$(python3 "$TOOL" --room "$ROOM" --names-only 2>"$TMP/e1.err"); RA=$?
B=$(WEDGE_ROOM="$ROOM" WEDGE_MODE=--names-only WEDGE_LAST="$TMP/live.txt" bash "$HELP" 2>"$TMP/e2.err"); RB=$?
echo "      bare rc=$RA names='$(printf '%s' "$A" | tr '\n' ',')' degraded=$(grep -c DEGRADED "$TMP/e1.err")"
echo "      helper rc=$RB persisted='$(tr '\n' ',' < "$TMP/live.txt")' note=$(grep -c 'retired agentId' "$TMP/e2.err")"
chk "E identical (no drift between the whips)" "$B" "$A"
chk "E live predicate rc is a real verdict, not DEGRADED" "$RA" "$([ -n "$A" ] && echo 0 || echo 1)"
chk "E no HARD twin on live DB" "$(python3 -c "
import importlib.util as u
s=u.spec_from_file_location('w','scripts/lane-wedge-check.py'); m=u.module_from_spec(s); s.loader.exec_module(m)
h,_=m.twins('$ROOM'); print(len(h))")" "0"
chk "E retired-id NOTEs survive the caller (not swallowed)" \
    "$([ "$(grep -c 'retired agentId' "$TMP/e2.err")" -ge 1 ] && echo yes || echo no)" "yes"
chk "E DEGRADED reason would survive the caller" \
    "$(WEDGE_ROOM=roomA WEDGE_DB="$TMP/twin.db" WEDGE_LAST="$TMP/last.txt" bash "$HELP" 2>&1 >/dev/null | grep -c 'owns 2 LIVE agentIds')" "1"

echo "--- F: orchestrator's OWN line, evaluated as written in the file"
sed -n '/^  WEDGED=/,+3p' scripts/group-orchestrator.sh > "$TMP/f.sh"
{
  printf 'ROOM=%q DB_GC=%q WEDGE_TOOL=%q WEDGE_LAST=%q\n' "$ROOM" "$LIVE_DB" "$TMP/broken.py" "$TMP/last.txt"
  cat "$TMP/f.sh"
  printf 'printf "WEDGED=%%s\\n" "$WEDGED"\n'
} > "$TMP/f2.sh"
bash "$TMP/f2.sh" > "$TMP/f.out" 2> "$TMP/f.err"
echo "      extracted: $(head -1 "$TMP/f.sh")"
echo "      result: $(cat "$TMP/f.out")  err='$(head -1 "$TMP/f.err")'"
grep -q 'DEGRADED' "$TMP/f.err" && ok "F orchestrator line says DEGRADED" || bad "F no DEGRADED from orchestrator line"
grep -q 'deadlane' "$TMP/f.out" && ok "F orchestrator line REUSED last known-good (fail closed)" \
  || bad "F orchestrator line produced an EMPTY list (fail OPEN)"

echo "--- G: syntax gates"
bash -n scripts/wedge-quarantine.sh && ok "G bash -n helper" || bad "G helper syntax"
bash -n scripts/kernel-room-nudge.sh && ok "G bash -n nudge" || bad "G nudge syntax"
bash -n scripts/group-orchestrator.sh && ok "G bash -n orchestrator" || bad "G orchestrator syntax"
python3 -c 'import ast;ast.parse(open("scripts/lane-wedge-check.py").read())' && ok "G py parse" || bad "G py parse"

echo
echo "RESULT: $([ "$FAIL" = 0 ] && echo ALL PASS || echo "$FAIL FAILURE(S)")   tmp=$TMP"
exit "$FAIL"
