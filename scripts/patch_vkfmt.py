#!/usr/bin/env python3
p = "/home/orangepi/mesa26/src/gallium/drivers/pvrgl/pvrgl_tq.c"
s = open(p).read()

# Fix the format arguments: the pbe helpers take VkFormat (they convert via
# vk_format_to_pipe_format internally), so passing PIPE_FORMAT_BGRA8888_UNORM
# directly indexes the pbe table with the WRONG entry -> packmode U32.
old = """      pvr_arch_pbe_get_src_format_and_gamma(
         PIPE_FORMAT_BGRA8888_UNORM,
         PVR_PBE_GAMMA_NONE,
         false,
         &surf_params.source_format,
         &surf_params.gamma);"""
new = """      pvr_arch_pbe_get_src_format_and_gamma(
         VK_FORMAT_B8G8R8A8_UNORM,
         PVR_PBE_GAMMA_NONE,
         false,
         &surf_params.source_format,
         &surf_params.gamma);"""
assert old in s, "srcfmt pattern not found"
s = s.replace(old, new)

old2 = """      surf_params.pbe_packmode = pvr_arch_get_pbe_packmode(
         PIPE_FORMAT_BGRA8888_UNORM);"""
new2 = """      surf_params.pbe_packmode = pvr_arch_get_pbe_packmode(
         VK_FORMAT_B8G8R8A8_UNORM);"""
assert old2 in s, "packmode pattern not found"
s = s.replace(old2, new2)

open(p, "w").write(s)
print("PATCHED vkformat args")
