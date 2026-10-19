#!/usr/bin/env python3
"""Restore a dropped `### BL-NN` item into the canonical queue from a backup, append-safe.

Why: the canonical queue (agentic-pool/BACKLOG.md) can lose an item's heading+body while
its `status:` lines still count healthy — 2nd/3rd occurrence of the 'raw repost over the
canonical file' defect. Heading count is the only honest integrity check.

Usage: tr-restore-bl20.py <BL-ID> [backup]
Inserts the de-escaped block before the following numbered heading (or appends).
Idempotent: refuses to act if the ID is already present in the live file.
"""
import re, shutil, subprocess, sys, time, pathlib

LIVE = pathlib.Path("/home/host/opikernel/agentic-pool/BACKLOG.md")
HEAD = re.compile(r'^#{2,4}(?:\s+#{2,4})?\s*(BL-\d+)\b')
STATE = re.compile(r'^status:\s*(\S+)')


def blocks(text):
    """Yield (id, start_line_idx, [lines]) for each BL block, escape-tolerant."""
    lines = text.splitlines(keepends=True)
    idx = []
    for i, ln in enumerate(lines):
        m = HEAD.match(ln)
        if m:
            idx.append((m.group(1), i))
    out = []
    for n, (bid, i) in enumerate(idx):
        j = idx[n + 1][1] if n + 1 < len(idx) else len(lines)
        out.append((bid, i, lines[i:j], lines[:i]))
    return out, lines


def deescape(ln):
    return re.sub(r'^(#{2,4})\s+#{2,4}\s+(BL-\d+)', r'\1 \2', ln)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "BL-20"
    bak = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(
        "/home/host/opikernel/agentic-pool/BACKLOG.md.bak-escape-20260920-215928")

    live = LIVE.read_text()
    if re.search(r'\b' + re.escape(target) + r'\b', live):
        print(f"REFUSE: {target} already present in live file (nothing to do)")
        return 2

    src = bak.read_text()
    src_blocks, _ = blocks(src)
    match = [b for b in src_blocks if b[0] == target]
    if not match:
        print(f"REFUSE: {target} not found in backup {bak}")
        return 3
    bid, _, body, _ = match[0]
    body = [deescape(l) for l in body]
    while body and not body[-1].strip():
        body.pop()
    body[-1] = body[-1].rstrip('\n') + '\n'

    live_blocks, live_lines = blocks(live)
    ids = [b[0] for b in live_blocks]
    # insert before the next higher BL-NN, else append
    num = int(target.split('-')[1])
    after = [(b[0], b[1]) for b in live_blocks if int(b[0].split('-')[1]) > num]
    ts = time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(LIVE, LIVE.with_suffix('.md.bak-pre-restore-' + ts))

    if after:
        at = after[0][1]
        new = live_lines[:at] + ['\n'] + body + live_lines[at:]
    else:
        new = live_lines + ['\n'] + body
    LIVE.write_text(''.join(new))
    print(f"OK: restored {bid} -> inserted before {after[0][0] if after else 'EOF'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
