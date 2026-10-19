#!/usr/bin/env python3
"""Diff DWARF struct layouts of same-named types across two pinctrl TUs.

Proves compile-time ABI drift inside one built-in.a: the same struct tag is
laid out differently depending on which header the TU included.
Usage: pinctrl-layout-diff.py <obj-or-vmlinux> ... [--filter substr]
"""
import subprocess
import sys
import re
from collections import defaultdict

MEMB = re.compile(r"DW_AT_name\s*:\s*(?:\(indirect string, offset: [^)]+\): )?(\S+)")
LOC = re.compile(r"DW_AT_data_member_location\s*:\s*(\d+)")
SIZE = re.compile(r"DW_AT_byte_size\s*:\s*(\d+)")


def parse(path, filt):
    out = subprocess.run(["objdump", "--dwarf=info", path],
                         capture_output=True, text=True, errors="replace").stdout
    types = {}
    cur = None
    pending_name = None
    for line in out.splitlines():
        if "DW_TAG_structure_type" in line or "DW_TAG_union_type" in line:
            cur = {"name": None, "size": None, "members": []}
            continue
        if cur is None:
            continue
        m = MEMB.search(line)
        if m:
            n = m.group(1)
            if "DW_AT_name" in line or "indirect string" in line:
                if "DW_TAG_member" in line:
                    cur["members"].append([n, None])
                elif cur["name"] is None:
                    cur["name"] = n
                    continue
        if "DW_TAG_member" in line and cur["members"] and cur["members"][-1][1] is None:
            pass
        s = SIZE.search(line)
        if s and "DW_AT_byte_size" in line:
            if "DW_TAG_member" in line and cur["members"] and cur["members"][-1][1] is None:
                cur["members"][-1][1] = int(s.group(1))  # bit size, fallback
            elif cur["size"] is None:
                cur["size"] = int(s.group(1))
        l = LOC.search(line)
        if l and cur["members"] and cur["members"][-1][1] is None:
            cur["members"][-1][1] = int(l.group(1)) * 8
        if cur["name"] and cur["members"] and "DW_TAG_structure_type" not in line:
            if cur["name"] not in types:
                types[cur["name"]] = cur
    return {k: v for k, v in types.items() if re.search(filt, k or "")}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    filt = "sunxi_pinctrl|soc_ver|pinctrl_desc"
    if "--filter" in sys.argv:
        filt = sys.argv[sys.argv.index("--filter") + 1]
    t = {p: parse(p, filt) for p in args}
    names = sorted({n for d in t.values() for n in d})
    for n in names:
        print(f"=== {n} ===")
        for p in args:
            e = t[p].get(n)
            if not e:
                print(f"  {p}: <not in DWARF>")
                continue
            mem = ",".join(f"{k}@{v}" for k, v in e["members"])
            print(f"  {p}: size={e['size']} {mem}")
        sizes = {t[p][n]["size"] for p in args if n in t[p]}
        if len(sizes) > 1:
            print("  *** LAYOUT MISMATCH ***")


if __name__ == "__main__":
    main()
