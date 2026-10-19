#!/bin/bash
# serial-symlink-audit.sh — inventory hardcoded /dev/ttyACM0 consumers + glob-style users.
cd /home/host/opikernel || exit 1

echo "=== glob-style ttyACM users (self-healing, leave alone) ==="
grep -rln 'ttyACM\*\|ttyACM\[0-9\]' --include='*.py' --include='*.sh' scripts/ pvrgl-work/ 2>/dev/null | grep -v '\.bak'

echo
echo "=== LIVE SET hardcoders ==="
LIVE="pvrgl-work/serial_single_owner.py
pvrgl-work/pipeline6_earlycon.py
pvrgl-work/pipeline7_bootonly.py
pvrgl-work/pipeline7_bootscr.py
pvrgl-work/pipeline8_bootscr.py
pvrgl-work/manual_boot_earlycon.py
pvrgl-work/pipeline4b.py
pvrgl-work/pipeline4.py
pvrgl-work/keeper_ctl.py
pvrgl-work/control.py
pvrgl-work/boot_attempt.sh
pvrgl-work/capture_serial.sh
pvrgl-work/boot_and_capture.sh
pvrgl-work/poke_board.sh
pvrgl-work/sercmd.py
pvrgl-work/serial_keeper.sh
pvrgl-work/ymodem_deploy.py
scripts/va39-gate-monitor.sh
scripts/kill-serial-runaways.py
scripts/agent-watchdog.sh
scripts/group-orchestrator.sh
scripts/serial_capture.py
scripts/serial_only_cycle.sh
scripts/clean_capture_cycle.sh
scripts/serial_catch_uboot.sh
scripts/claim-serial-port.sh"

for f in $LIVE; do
  [ -f "$f" ] || continue
  n=$(grep -c 'ttyACM0' "$f" 2>/dev/null || echo 0)
  printf '%-44s %2s hits  %s\n' "$f" "$n" "$(stat -c %y "$f" | cut -d' ' -f1)"
done

echo
echo "=== FULL repo count of files with a literal /dev/ttyACM0 ==="
grep -rl '/dev/ttyACM0' --include='*.py' --include='*.sh' . 2>/dev/null | grep -v '\.bak' | wc -l
