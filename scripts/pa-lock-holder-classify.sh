#!/bin/bash
# PA dry-run: classify every holder of the orchestrator lock fd (8)
LOCK=/home/host/opikernel/state/group-orchestrator.lock
echo "=== MY OWN ancestry (must never be killed) ==="
p=$$; while [ "$p" -gt 1 ]; do printf '  %s %s\n' "$p" "$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | cut -c1-70)"; p=$(awk '{print $4}' /proc/$p/stat 2>/dev/null); done
echo "=== lock holders (fd 8) ==="
for pid in $(fuser "$LOCK" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$'); do
  CMD=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | cut -c1-95)
  PARENT=$(awk '{print $4}' /proc/$pid/stat 2>/dev/null)
  ET=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
  SELF=$(readlink -f /proc/$pid/cwd 2>/dev/null)
  case "$CMD" in
    *yolo-query*) TAG="YOLO-SPAWN  -> reap candidate" ;;
    *group-orchestrator*) TAG="DAEMON      -> restart target" ;;
    *) TAG="OTHER       -> leave alone" ;;
  esac
  printf '  pid=%-8s ppid=%-8s etime=%-9s %s\n      %s\n' "$pid" "$PPID" "$ET" "$TAG" "$CMD"
done
echo "=== counts ==="
echo "  fd8 holders          : $(fuser $LOCK 2>/dev/null | tr ' ' '\n' | grep -cE '^[0-9]+$')"
echo "  live yolo-query procs: $(pgrep -f yolo-query | wc -l)"
echo "  syntax               : $(bash -n /home/host/opikernel/scripts/group-orchestrator.sh && echo OK)"
echo "  script md5           : $(md5sum /home/host/opikernel/scripts/group-orchestrator.sh | cut -d' ' -f1)"
