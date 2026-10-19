#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()
old = """         unsigned spx = dst->base.width0;      /* pixels per row */
         unsigned ls = spx > 1 ? (spx - 1) / 2 : 0;"""
new = """         unsigned spx = dst->base.width0;      /* pixels per row */
         unsigned ls = 127;                      /* EXPERIMENT value */"""
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("PATCHED ls=127")
