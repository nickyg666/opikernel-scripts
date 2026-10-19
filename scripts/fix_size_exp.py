#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()
old = """         unsigned sx = int(math.log2(dst->base.width0)) if dst->base.width0 > 0 else 0;
         unsigned sy = int(math.log2(dst->base.height0)) if dst->base.height0 > 0 else 0;"""
new = """         unsigned sx = 0, sy = 0;
         while ((1u << sx) < dst->base.width0 && sx < 15) sx++;
         while ((1u << sy) < dst->base.height0 && sy < 15) sy++;"""
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("FIXED ternary")
