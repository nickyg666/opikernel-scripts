#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()

# Revert the twiddled hack back to LINEAR
old = """      surf_params.addr.addr = dst->dev_addr;
      /* FIXME(linear-path): the upstream linear transfer path faults on
       * this kernel (vulkan linear clear faults identically). A solid
       * clear is layout-agnostic, so claim TWIDDLED to take the working
       * path; the PBE writes red in twiddle order and every pixel is red. */
      surf_params.mem_layout = PVR_MEMLAYOUT_TWIDDLED;"""
new = """      surf_params.addr.addr = dst->dev_addr;
      surf_params.mem_layout = PVR_MEMLAYOUT_LINEAR;"""
assert old in s, "twiddled pattern not found"
s = s.replace(old, new)

# Experiment: override the linestride field in MRY0 for the linear path.
old2 = """      pvr_arch_pbe_pack_state(dev_info, &surf_params, &render_params,
                              pbe_words, &regs->pbe_wordx_mrty[0]);

      /* EXPERIMENT: linear transfers leave size_x/y = 0 (1_PIXEL), which
       * the FW apparently uses for surface-width addressing -> sparse
       * pixel output + overrun past the surface.  Force the size fields
       * as if the surface were twiddled and see if the pattern changes. */
      {
         uint64_t m1 = regs->pbe_wordx_mrty[1];
         unsigned sx = 0, sy = 0;
         while ((1u << sx) < dst->base.width0 && sx < 15) sx++;
         while ((1u << sy) < dst->base.height0 && sy < 15) sy++;
         m1 |= ((uint64_t)(sx & 0xF) << 60);
         m1 |= ((uint64_t)(sy & 0xF) << 28);
         regs->pbe_wordx_mrty[1] = m1;
         mesa_logi("pvrgl: EXPERIMENT forced size_x=%u size_y=%u mry1=0x%llx",
                   sx, sy, (unsigned long long)m1);
      }"""
new2 = """      pvr_arch_pbe_pack_state(dev_info, &surf_params, &render_params,
                              pbe_words, &regs->pbe_wordx_mrty[0]);

      /* EXPERIMENT: force linestride to pixel-based value (stride_px-1)/2.
       * The FW may interpret the linear linestride field differently. */
      {
         uint64_t m0 = regs->pbe_wordx_mrty[0];
         unsigned spx = dst->base.width0;      /* pixels per row */
         unsigned ls = spx > 1 ? (spx - 1) / 2 : 0;
         m0 &= ~(0xFFFFULL << 34);
         m0 |= ((uint64_t)(ls & 0xFFFF) << 34);
         regs->pbe_wordx_mrty[0] = m0;
         mesa_logi("pvrgl: EXPERIMENT linestride=%u (px=%u) mry0=0x%llx",
                   ls, spx, (unsigned long long)m0);
      }"""
assert old2 in s, "experiment pattern not found"
s = s.replace(old2, new2)
open(p, "w").write(s)
print("PATCHED linestride experiment")
