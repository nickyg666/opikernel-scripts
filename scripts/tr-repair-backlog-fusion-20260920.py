#!/usr/bin/env python3
"""Surgical repair of the canonical queue after the 2026-09-20 22:11 raw-repost write.

Defect (found by TelegramRunner's heading-count integrity check, not state counts):
  - BL-20's heading+status were destroyed and its body stayed fused to the tail of BL-19's block
    -> 23 headings for 24 items.
  - BL-16's live debugger claim (claimed-at 2026-09-21 01:53:07 UTC) was pasted unheaded into
    BL-19's block while BL-16 itself still read `status: open`.
  - Net: 25 `status:` lines for 23 headings.

Repair: prove the fused BL-20 body is identical to the restored BL-20 block, delete the fused copy,
move debugger's claim onto the real BL-16 block, land 24 headings / 24 status lines.
In-place, back-to-front edits (no re-concatenation). Idempotent: no-ops if already repaired.
"""
import difflib, pathlib, re, shutil, sys, time

F = pathlib.Path("/home/host/opikernel/agentic-pool/BACKLOG.md")
lines = F.read_text().splitlines(keepends=True)
HEAD = re.compile(r'^### BL-(\d+)\b')
ST = re.compile(r'^status:')

pos = [(i, m.group(1)) for i, l in enumerate(lines) if (m := HEAD.match(l))]
blocks = {}
for n, (i, bid) in enumerate(pos):
    blocks[bid] = (i, pos[n + 1][0] if n + 1 < len(pos) else len(lines))

i19, e19 = blocks['19']
i20, e20 = blocks['20']
i16, e16 = blocks['16']

seg_start = next(i for i in range(i19, e19) if lines[i].startswith('status: done'))
seg_end = next(i for i in range(seg_start + 1, e19) if ST.match(lines[i]))
bl16_seg = lines[seg_start:seg_end]
fused_b20 = lines[seg_end:e19]
restored_b20 = lines[i20:e20]

if 'BOOT BLOCKER' not in restored_b20[0]:
    sys.exit("REFUSE: restored BL-20 block not where expected")
if 'fdt blob at 0x43880000' not in ''.join(bl16_seg):
    sys.exit("REFUSE: BL-16 pasted segment not identified")


HDR = re.compile(r'^(status:|claimed-by:|claimed-at:|filed-by:|#)')


def body_of(ls):
    """Drop the leading metadata header, keep the substantive body."""
    i = 0
    while i < len(ls) and (not ls[i].strip() or HDR.match(ls[i])):
        i += 1
    return [l.rstrip() for l in ls[i:] if l.strip()]


fb, rb = body_of(fused_b20), body_of(restored_b20)
d = list(difflib.unified_diff(fb, rb, lineterm='', n=0))
print("fused_body=%d restored_body=%d body_diff_lines=%d" % (len(fb), len(rb), len(d)))
for l in d[:8]:
    print("  DIFF " + l)
if d:
    sys.exit("REFUSE: bodies differ -- not deleting content")

claim_by = next(l for l in bl16_seg if l.startswith('claimed-by:'))
claim_at = next(l for l in bl16_seg if l.startswith('claimed-at:'))
ev = next((l for l in bl16_seg if l.startswith('evidence:')), None)

# NEVER overwrite a live claim: the pasted segment is only authoritative when the real block is
# unclaimed ("(none" / "—"). A sibling may have written a newer claim straight into this block
# between our read and this edit -- that write wins, and this script must refuse instead of clobbering.
live_claim = [l for l in lines[i16:e16]
              if l.startswith('claimed-by:') and '(none' not in l]
if live_claim:
    sys.exit("REFUSE: BL-16 already has a live claim (%s) -- pasted claim is stale, not applied"
             % live_claim[0].strip())

new16 = []
seen_by = seen_at = False
for l in lines[i16:e16]:
    if l.startswith('status: open'):
        new16.append('status: claimed\n')
    elif l.startswith('claimed-by:') and not seen_by:
        new16.append(claim_by)
        seen_by = True
    elif l.startswith('claimed-at:') and not seen_at:
        new16.append(claim_at)
        seen_at = True
    else:
        new16.append(l)
if ev and not any(l.startswith('evidence:') for l in new16):
    new16.append(ev)

ts = time.strftime('%Y%m%d-%H%M%S')
shutil.copy2(F, F.with_suffix('.md.bak-surgery-' + ts))

# back-to-front: (1) drop fused BL-20 copy + pasted BL-16 segment from BL-19's block
del lines[seg_start:e19]
# (2) swap BL-16's block (indices before seg_start are unchanged)
lines[i16:e16] = new16

F.write_text(''.join(lines))
txt = F.read_text()
h = len(re.findall(r'^### BL-\d+', txt, re.M))
s = len(re.findall(r'^status:', txt, re.M))
print("headings=%d status_lines=%d" % (h, s))
print("BL-20_copies=%d  BL-16=%s" % (
    txt.count('BOOT BLOCKER: BSP pinctrl probe'),
    re.search(r'### BL-16.*?\n(status: \S+)\n', txt, re.S).group(1)))
print("md5 %s" % __import__('hashlib').md5(txt.encode()).hexdigest())
