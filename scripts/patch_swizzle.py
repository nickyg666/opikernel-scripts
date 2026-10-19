#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()

old = """      /* B8G8R8A8_UNORM channel swizzle X,Y,Z,W (memory-order BGRA). */
      surf_params.swizzle[0] = 0; /* X */
      surf_params.swizzle[1] = 1; /* Y */
      surf_params.swizzle[2] = 2; /* Z */
      surf_params.swizzle[3] = 3; /* W */"""
new = """      /* Channel swizzle from the format table: B8G8R8A8 maps the PBE's
       * RGBA source onto BGRA memory (upstream pvr_pbe_setup_codegen_defaults
       * uses pvr_get_format_swizzle(); a hardcoded identity writes R into
       * the B byte -> blue clears). */
      {
         const uint8_t *swz = pvr_get_format_swizzle(VK_FORMAT_B8G8R8A8_UNORM);
         memcpy(surf_params.swizzle, swz, sizeof(surf_params.swizzle));
      }"""
assert old in s, "swizzle pattern not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("PATCHED swizzle")
