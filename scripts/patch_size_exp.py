#!/usr/bin/env python3
import math
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()

old = """      pvr_arch_pbe_pack_state(dev_info, &surf_params, &render_params,
                              pbe_words, &regs->pbe_wordx_mrty[0]);
   }"""
new = """      pvr_arch_pbe_pack_state(dev_info, &surf_params, &render_params,
                              pbe_words, &regs->pbe_wordx_mrty[0]);

      /* EXPERIMENT: linear transfers leave size_x/y = 0 (1_PIXEL), which
       * the FW apparently uses for surface-width addressing -> sparse
       * pixel output + overrun past the surface.  Force the size fields
       * as if the surface were twiddled and see if the pattern changes. */
      {
         uint64_t m1 = regs->pbe_wordx_mrty[1];
         unsigned sx = int(math.log2(dst->base.width0)) if dst->base.width0 > 0 else 0;
         unsigned sy = int(math.log2(dst->base.height0)) if dst->base.height0 > 0 else 0;
         m1 |= ((uint64_t)(sx & 0xF) << 60);
         m1 |= ((uint64_t)(sy & 0xF) << 28);
         regs->pbe_wordx_mrty[1] = m1;
         mesa_logi("pvrgl: EXPERIMENT forced size_x=%u size_y=%u mry1=0x%llx",
                   sx, sy, (unsigned long long)m1);
      }
   }"""
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("PATCHED size experiment")
