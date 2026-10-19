#!/bin/bash
# PA: relaunch the group orchestrator loop detached, after editing
# scripts/group-orchestrator.sh (the running bash keeps reading the OLD inode, so
# an in-place edit does not take effect until the loop is restarted).
# Same invocation + same log sink the 02:22 process used (verified via /proc/<pid>/fd/1).
LOG=/home/host/opikernel/logs/group-orchestrator.log
setsid /bin/bash /home/host/opikernel/scripts/group-orchestrator.sh >>"$LOG" 2>&1 </dev/null &
echo "started pid=$!"
