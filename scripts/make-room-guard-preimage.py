#!/usr/bin/env python3
"""Build a TRUE pre-edit image of scripts/webui-room-msg-guard.py by reversing the
4 documented hunks added at 2026-09-20 20:11 (the file is untracked in git, so
`git show HEAD:` produced a post-edit copy and was useless as a rollback point).

Usage: python3 scripts/make-room-guard-preimage.py   -> writes <f>.pre-20260920-2011
Then `diff` the result against the current file; the only differences must be the
4 hunks below.
"""
import pathlib
import sys

SRC = pathlib.Path("/home/host/opikernel/scripts/webui-room-msg-guard.py")
DST = SRC.with_name(SRC.name + ".pre-20260920-2011")

txt = SRC.read_text()

hunks = [
    # 1. WINDOW_MIN constant
    ('DRY_RUN = os.environ.get("ROOM_GUARD_DRY", "") not in ("", "0", "no", "false")\n'
     'WINDOW_MIN = int(os.environ.get("ROOM_GUARD_WINDOW_MIN", "30"))\n',
     'DRY_RUN = os.environ.get("ROOM_GUARD_DRY", "") not in ("", "0", "no", "false")\n'),
    # 2. docstring item 6
    ('  5. Prints ONE summary line per room; prints nothing when nothing to do.\n'
     '  6. Prints a `WEDGE <room> N stuck lane(s)` line for any (room,agent) with\n'
     '     >=3 enqueues and 0 starts inside WINDOW_MIN — the per-key drain wedge the\n'
     '     room-wide eligible count cannot see (see stuck_lanes()).\n',
     '  5. Prints ONE summary line per room; prints nothing when nothing to do.\n'),
    # 3. stuck_lanes() + the blank lines around it
    ('\n\ndef stuck_lanes(con, rooms, window_min=WINDOW_MIN, min_enq=3):\n',
     '\n\n@@STUCK_LANES_START@@\n'),
    # 4. main() wiring
    ('    zombies = reap_running(con)\n    wedges = stuck_lanes(con, rooms)\n',
     '    zombies = reap_running(con)\n'),
    ('    lines.extend(wedges)\n', ''),
]

for old, new in hunks:
    assert old in txt, f"hunk not found: {old[:60]!r}"
    txt = txt.replace(old, new, 1)

# cut the whole stuck_lanes body between the markers
start = txt.index("@@STUCK_LANES_START@@")
# the function ran until the line "    return out\n" followed by two newlines + "def guard_room"
end = txt.index("def guard_room(con, room):", start)
txt = txt[:start] + "\n\n" + txt[end:]

DST.write_text(txt)
print(f"wrote {DST} ({len(txt)} B)")
print("WEDGE present:", "WEDGE" in txt, "| stuck_lanes present:", "stuck_lanes" in txt)
sys.exit(0)
