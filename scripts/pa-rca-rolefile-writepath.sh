#!/usr/bin/env bash
# PA bounded action: find the code path that writes agentic-pool/<role>.md
# so a failed gc-post can never clobber a role file again.
set -u
cd /home/host/opikernel
echo "== doer scripts referencing agentic-pool =="
grep -rln "agentic-pool" scripts/ 2>/dev/null | sort | head -40
echo
echo "== files that WRITE into agentic-pool (redirect / tee / python open) =="
grep -rnE '(>>?|\btee\b|-o ) *"?[^"]*agentic-pool' scripts/ 2>/dev/null | grep -vE '^\S+:[0-9]+: *#' | head -40
echo
echo "== python writers =="
grep -rnE "agentic-pool" scripts/*.py 2>/dev/null | grep -nE "open\(|write_text|write\(|Path\(" | head -40
echo
echo "== nudge script write lines =="
grep -nE "agentic-pool|ROLE|role_file|EOF|cat >|tee" scripts/kernel-room-nudge.sh 2>/dev/null | head -40
