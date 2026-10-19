#!/usr/bin/env python3
"""Interpret PVRDBG/PVRCTX dmesg output from the M3 probe run and print the
exact kernel fix to apply. Feed it the dmesg tail after deploy_m3_probe.sh.

Usage: python3 interpret_m3_output.py [dmesg_file]   (default: stdin)
"""
import sys
import re

lines = sys.stdin.read().splitlines() if len(sys.argv) < 2 else open(sys.argv[1]).read().splitlines()

dbg = [l for l in lines if "PVRDBG" in l or "PVRCTX" in l]
if not dbg:
    print("NO PVRDBG/PVRCTX LINES FOUND — module not instrumented, not loaded, or probe never ran.")
    sys.exit(1)

for l in dbg:
    print(l.strip())

print("\n=== ANALYSIS ===")
joined = "\n".join(dbg)
failed = False

def fail(msg):
    global failed
    failed = True
    print(msg)

# PVRCTX arg dump
m = re.search(r"PVRCTX type=(\d+) prio=(\d+) flags=(\d+) vm=(\d+) cs=(\d+) len=(\d+)", joined)
if m:
    typ, prio, flags, vm, cs, ln = m.groups()
    print(f"[entry] type={typ} prio={prio} flags={flags} vm={vm} cs=0x{int(cs):x} len={ln} — probe reached kernel create_context")
    if flags != "0":
        fail("  FIX: probe passing flags!=0 — kernel rejects (must be 0)")

# frag_state queries
for m in re.finditer(r"PVRDBG frag_state: xe=(\d+) mc=(\d+) nrp_err=(-?\d+) nrp=(\d+)", joined):
    xe, mc, nrp_err, nrp = m.groups()
    if nrp_err != "0":
        fail(f"  FAIL: xe_memory_hierarchy branch — PVR_FEATURE_VALUE(num_raster_pipes) err={nrp_err}")
        fail("  FIX: get_frag_ctx_state_size fallback — when num_raster_pipes missing use num_isp_ipp_pipes or 1")
for m in re.finditer(r"PVRDBG frag_state: niip_err=(-?\d+) niip=(\d+)", joined):
    niip_err, niip = m.groups()
    if niip_err != "0":
        fail(f"  FAIL: non-xe branch — PVR_FEATURE_VALUE(num_isp_ipp_pipes) err={niip_err}")
        fail("  FIX: get_frag_ctx_state_size fallback — num_isp_ipp_pipes missing on BXM; use 1")

# queue_create
for m in re.finditer(r"PVRDBG queue_create: type=(\d+) ctx_type=(\d+) get_state_size=(-?\d+)", joined):
    typ, ctype, sz = m.groups()
    if int(sz) < 0:
        fail(f"  FAIL: queue type={typ} (ctx {ctype}) get_ctx_state_size returned {sz} — feature query failed above")
        fail("  FIX: as per frag_state above (or GEOMETRY constant if type=0 failed)")
for m in re.finditer(r"PVRDBG queue_create: type=(\d+) ctx_type=(\d+) state_size=(\d+) err=(-?\d+)", joined):
    typ, ctype, sz, err = m.groups()
    if err != "0":
        fail(f"  FAIL: queue type={typ} (ctx {ctype}) pvr_fw_object_create err={err} size={sz}")

# fw object path
m = re.search(r"PVRDBG fw_obj_gem_create: size=(\d+) flags=([0-9a-fx]+) err=(-?\d+)", joined)
if m:
    sz, fl, err = m.groups()
    if err != "0":
        fail(f"  FAIL: pvr_gem_object_create(size={sz}, flags={fl}) err={err} — pvr_gem.c:356 (size==0 || invalid flags)")
        fail("  FIX: check ctx state size non-zero + flags valid (FW flags: DEVICE_UNCACHED|PM_FW_PROTECT)")
m = re.search(r"PVRDBG fw_obj_fw_map: size=(\d+) flags=([0-9a-fx]+) dev_addr=([0-9a-fx]+) err=(-?\d+)", joined)
if m:
    sz, fl, da, err = m.groups()
    if err != "0":
        fail(f"  FAIL: pvr_fw_object_fw_map err={err} dev_addr={da}")
m = re.search(r"PVRDBG fw_map_insert: size=(\d+) heap=\[([0-9a-fx]+)\.\.([0-9a-fx]+)\] err=(-?\d+)", joined)
if m:
    sz, lo, hi, err = m.groups()
    if err != "0":
        fail(f"  FAIL: drm_mm_insert_node_in_range err={err} (ENOSPC={err == '-28'}) size={sz} heap=[{lo}..{hi}]")
        fail("  FIX: FW heap full — mesa-vulkan pre-init allocates FW objects (free lists/HWRT) the bare probe skips;")
        fail("       either replicate pre-init in probe or accept winsys-provided ctx (pvrgl uses winsys already)")
m = re.search(r"PVRDBG fw_map_reserve: addr=([0-9a-fx]+) size=(\d+) err=(-?\d+)", joined)
if m:
    if m.group(3) != "0":
        fail(f"  FAIL: drm_mm_reserve_node err={m.group(3)} addr={m.group(1)}")
m = re.search(r"PVRDBG fw_map_vmmap: err=(-?\d+)", joined)
if m:
    if m.group(1) != "0":
        fail(f"  FAIL: fw vm_map err={m.group(1)} — MMU page-table issue")

print("\n=== VERDICT ===")
if "PVRDBG queue_create" not in joined and "PVRCTX" in joined:
    print("Queues never created → failure between PVRCTX entry and pvr_queue_create (get_fw_obj_size / vm_lookup / remap_priority).")
elif failed:
    print("See FAIL lines above; apply the corresponding kernel patch in host-build, rebuild, redeploy.")
else:
    print("All instrumented sites passed — check probe exit code / full dmesg for the real errno (job submit path).")
