#!/usr/bin/env bash
# PA: quarantine the nudge-error junk files out of the role-file namespace so
# `find agentic-pool -maxdepth 1 -name '*.md' -size -300c` is a clean detector
# and no nudge agent can mistake a failure log for a role definition.
set -u
cd /home/host/opikernel/agentic-pool
D=_rolefile-junk-20260920
mkdir -p "$D"
for f in error.md error_mti5ax1clq0zlx.md unknown.md unknown_role.md \
         unknown_role_for_room_mti5ax1clq0zlx.md mti3yr2g3yjpyr.md; do
  if [ -f "$f" ]; then
    sz=$(stat -c%s "$f")
    mv -v "$f" "$D/$f"
    printf '%s\t%s B\t%s\n' "$(md5sum "$D/$f" | cut -c1-8)" "$sz" "$f" >> "$D/MANIFEST.txt"
  fi
done
echo "--- manifest ---"; cat "$D/MANIFEST.txt"
echo "--- remaining small .md in agentic-pool (should be only real role stubs) ---"
find . -maxdepth 1 -name '*.md' -size -300c -printf '%s B\t%f\n' | sort -n
