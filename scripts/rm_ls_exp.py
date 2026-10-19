#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()
old = """      /* EXPERIMENT: force linestride to pixel-based value (stride_px-1)/2.
       * The FW may interpret the linear linestride field differently. */
      {
         uint64_t m0 = regs->pbe_wordx_mrty[0];
         unsigned spx = dst->base.width0;      /* pixels per row */
         unsigned ls = 127;                      /* EXPERIMENT value */
         m0 &= ~(0xFFFFULL << 34);
         m0 |= ((uint64_t)(ls & 0xFFFF) << 34);
         regs->pbe_wordx_mrty[0] = m0;
         mesa_logi("pvrgl: EXPERIMENT linestride=%u (px=%u) mry0=0x%llx",
                   ls, spx, (unsigned long long)m0);
      }"""
new = """"""
assert old in s, "linestride experiment not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("REMOVED linestride experiment")
