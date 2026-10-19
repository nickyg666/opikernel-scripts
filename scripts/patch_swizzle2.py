#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()
old = """      /* Channel swizzle from the format table: B8G8R8A8 maps the PBE's
       * RGBA source onto BGRA memory (upstream pvr_pbe_setup_codegen_defaults
       * uses pvr_get_format_swizzle(); a hardcoded identity writes R into
       * the B byte -> blue clears). */
      {
         const uint8_t *swz = pvr_get_format_swizzle(VK_FORMAT_B8G8R8A8_UNORM);
         memcpy(surf_params.swizzle, swz, sizeof(surf_params.swizzle));
      }"""
new = """      /* Channel swizzle for BGRA memory: the PBE source is RGBA (clear
       * registers), so map B<-R, R<-B (upstream uses pvr_get_format_swizzle,
       * which is not linked into pvrgl; B8G8R8A8 == {Z,Y,X,W} = {2,1,0,3}). */
      surf_params.swizzle[0] = 2; /* B <- source Z (blue from red slot) */
      surf_params.swizzle[1] = 1; /* G <- source Y */
      surf_params.swizzle[2] = 0; /* R <- source X */
      surf_params.swizzle[3] = 3; /* A <- source W */"""
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("PATCHED swizzle inline")
