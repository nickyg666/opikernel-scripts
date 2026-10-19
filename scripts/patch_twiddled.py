#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()

# Flip the clear surface to TWIDDLED: the upstream linear transfer path is
# broken on this kernel (upstream vulkan linear clear faults identically),
# but a SOLID COLOR clear is layout-agnostic — red is red in any order.
old = """      surf_params.addr.addr = dst->dev_addr;
      surf_params.mem_layout = PVR_MEMLAYOUT_LINEAR;"""
new = """      surf_params.addr.addr = dst->dev_addr;
      /* FIXME(linear-path): the upstream linear transfer path faults on
       * this kernel (vulkan linear clear faults identically). A solid
       * clear is layout-agnostic, so claim TWIDDLED to take the working
       * path; the PBE writes red in twiddle order and every pixel is red. */
      surf_params.mem_layout = PVR_MEMLAYOUT_TWIDDLED;"""
assert old in s, "memlayout pattern not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("PATCHED twiddled clear")
