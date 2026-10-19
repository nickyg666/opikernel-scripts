#!/bin/bash
# flock contention proof for the orchestrator single-instance guard.
LOCK=/home/host/opikernel/state/group-orchestrator.lock
python3 - "$LOCK" <<'PY' &
import fcntl, sys, time
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
print("HOLDER: lock acquired, holding 12s", flush=True)
time.sleep(12)
print("HOLDER: releasing", flush=True)
PY
holder=$!
sleep 2
echo "--- second instance while lock is HELD ---"
timeout 60 /home/host/opikernel/scripts/group-orchestrator.sh
echo "rc=$?"
wait $holder
echo "--- third instance after the holder released ---"
ORCH_LOCK="$LOCK" timeout 90 /home/host/opikernel/scripts/group-orchestrator.sh
echo "rc=$?"
