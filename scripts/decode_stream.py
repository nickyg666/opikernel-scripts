#!/usr/bin/env python3
"""Decode a pvr transfer fw stream using the kernel defs order, print fields."""
import sys

def decode(name, hexstr):
    ws = hexstr.split()
    assert ws[0] == "000000b0", f"{name}: bad hdr {ws[0]}"
    w = ws[2:]  # skip hdr (len + pad)
    i = 0
    def take64(label):
        nonlocal i
        lo, hi = w[i], w[i+1]
        i += 2
        print(f"  {label}: 0x{hi}{lo}")
    def take32(label):
        nonlocal i
        v = w[i]
        i += 1
        print(f"  {label}: 0x{v}")
    print(f"== {name} ==")
    take64("pds_bgnd0_base")
    take64("pds_bgnd1_base")
    take64("pds_bgnd3_sizeinfo")
    take64("isp_mtile_base")
    for k in range(9):
        take64(f"pbe_wordx_mrty[{k}]")
    take32("isp_bgobjvals")
    take32("usc_pixel_output_ctrl")
    take32("usc_clear_register0")
    take32("usc_clear_register1")
    take32("usc_clear_register2")
    take32("usc_clear_register3")
    take32("isp_mtile_size")
    take32("isp_render_origin")
    take32("isp_ctl")
    take32("isp_aa")
    take32("event_pixel_pds_info")
    take32("event_pixel_pds_code")
    take32("event_pixel_pds_data")
    take32("isp_render")
    take32("isp_rgn")
    take32("frag_screen")
    print(f"  [consumed {i} words of {len(w)}]")
    if i < len(w):
        print(f"  EXTRA: {' '.join(w[i:])}")

golden = "000000b0 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 68800000 020000fd 7000007f 7000007f 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00007ff8 ff0000ff 00000000 00000000 00000000 00080008 00000000 00025000 00000000 00000202 00002620 00002600 00000003 00000000 007f007f"
ours = "000000b0 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00001000 00000000 68800000 020003fc 0000007f 0000007f 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00007ff8 ff0000ff 00000000 00000000 00000000 00080008 00000000 00025000 00000000 00000202 00002010 00002000 00000003 00000000 007f007f"

decode("GOLDEN (vulkan, works)", golden)
print()
decode("OURS (pvrgl, faults)", ours)
