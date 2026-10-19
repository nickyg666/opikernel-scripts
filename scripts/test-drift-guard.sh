#!/bin/bash
# test-drift-guard.sh — verify detection + action paths without touching production
set -u
cd /home/host
FIX=/tmp/driftfix.db
STATE=/tmp/driftfix.state.json
FIXSTATE=/tmp/driftfix-statedb.db
rm -f "$FIX" "$FIXSTATE" "$STATE"
cp /home/host/.hermes-web-ui/hermes-web-ui.db "$FIX"
cp /home/host/.hermes/state.db "$FIXSTATE"

echo "=== inject a synthetic drift: one message whose body repeats a line 6x ==="
python3 - "$FIX" <<'PYEOF'
import sqlite3, sys, time, json
db = sys.argv[1]
con = sqlite3.connect(db)
now = int(time.time() * 1000)
blob = "\n".join(["driftfixture-agent：**Rebuild started** via scripts/kdir-build.sh."] * 6)
con.execute("""insert into gc_messages (roomId,senderId,senderName,senderType,content,timestamp,mentions,role)
               values ('mti5ax1clq0zlx','x','driftfixture-agent','agent',?,?, '[]','assistant')""",
            (blob, now - 60_000))
clean = ["driftfixture-clean: step %d — ran cmd, rc=0, md5=abc%d" % (i, i) for i in range(5)]
for i, c in enumerate(clean):
    con.execute("""insert into gc_messages (roomId,senderId,senderName,senderType,content,timestamp,mentions,role)
                   values ('mti5ax1clq0zlx','x','driftfixture-clean','agent',?,?, '[]','assistant')""",
                (c, now - 60_000 + i))
con.commit(); con.close()
print("injected 6x-repeat blob for driftfixture-agent + 5 distinct msgs for driftfixture-clean")
PYEOF

echo
echo "=== DRY RUN against fixture (--explain) ==="
DRIFT_DB="$FIX" DRIFT_STATE_DB="$FIXSTATE" DRIFT_STATE="$STATE" \
  python3 /home/host/opikernel/scripts/agent-drift-guard.py --explain --agent driftfixture-agent --agent driftfixture-clean

echo
echo "=== DRY RUN, cross-message repeat signal (3 identical messages) ==="
python3 - "$FIX" <<'PYEOF'
import sqlite3, sys, time
con = sqlite3.connect(sys.argv[1]); now = int(time.time() * 1000)
for i in range(3):
    con.execute("""insert into gc_messages (roomId,senderId,senderName,senderType,content,timestamp,mentions,role)
                   values ('mti5ax1clq0zlx','x','driftfixture-xmsg','agent',?,?,'[]','assistant')""",
        ("Same exact output posted three times by driftfixture-xmsg — long enough body to count.", now - 30_000 + i))
con.commit(); con.close(); print("injected 3 identical messages")
PYEOF
DRIFT_DB="$FIX" DRIFT_STATE_DB="$FIXSTATE" DRIFT_STATE="$STATE" \
  python3 /home/host/opikernel/scripts/agent-drift-guard.py --explain --agent driftfixture-xmsg

echo
echo "=== APPLY against fixture with --no-dispatch (state + queue writes go to fixture) ==="
DRIFT_DB="$FIX" DRIFT_STATE_DB="$FIXSTATE" DRIFT_STATE="$STATE" \
  python3 /home/host/opikernel/scripts/agent-drift-guard.py --apply --no-dispatch --agent driftfixture-agent
echo "--- fixture queue rows for that agent (expect none) / state.json written: ---"
cat "$STATE" 2>/dev/null || echo "(no state file)"

echo
echo "=== bridge interrupt protocol (real bridge, session that does not exist) ==="
python3 - <<'PYEOF'
import glob, json, socket
for ep in sorted(glob.glob("/tmp/hermes-agent-bridge-workers/*.sock")):
    def call(req):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(10)
        s.connect(ep); s.sendall((json.dumps(req)+"\n").encode())
        d = s.recv(65536).decode().split("\n")[0]; s.close(); return json.loads(d)
    print("ping   ->", {k: call({"action":"ping"}).get(k) for k in ("ok","profile","session_count","running_session_count")})
    print("interrupt(nonexistent) ->", call({"action":"interrupt","session_id":"no-such-session","message":"drift guard probe"}))
PYEOF

echo
echo "=== production DB dry run (must NOT flag anything on clean data) ==="
python3 /home/host/opikernel/scripts/agent-drift-guard.py
