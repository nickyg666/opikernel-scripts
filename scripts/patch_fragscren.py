#!/usr/bin/env python3
import sys
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()

old = """   /* ---- fw stream pack [ref :5810]. ---- */"""
new = """   /* ---- Fragment screen [ref :3023]: the FW needs the render
    * dimensions in CR_FRAG_SCREEN or the ISP screen grid is degenerate
    * (xmax=ymax=0, sparse pixel output). ---- */
   if (PVR_HAS_FEATURE(dev_info, gpu_multicore_support)) {
      pvr_csb_pack (&regs->frag_screen, CR_FRAG_SCREEN, reg) {
         reg.xmax = dst->base.width0 ? dst->base.width0 - 1 : 0;
         reg.ymax = dst->base.height0 ? dst->base.height0 - 1 : 0;
      }
   }

   /* ---- fw stream pack [ref :5810]. ---- */"""
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("PATCHED frag_screen")
