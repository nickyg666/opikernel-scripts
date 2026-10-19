#!/usr/bin/env python3
"""Fix mangled instrumentation: wrap `printk(...); return -EINVAL;` into a
proper braced block so the return stays inside the original if().

Mangled form produced by fuzzy patch tool:
    if (cond)
        printk(KERN_ERR "PVRDBG %s:%d\n", __func__, __LINE__); return -EINVAL;

Correct form:
    if (cond) {
        printk(KERN_ERR "PVRDBG %s:%d\n", __func__, __LINE__);
        return -EINVAL;
    }
"""
import re
import sys

FILES = [
    "/home/host/kernel-trees/host-build/mainline-6.18/drivers/gpu/drm/imagination/pvr_context.c",
    "/home/host/kernel-trees/host-build/mainline-6.18/drivers/gpu/drm/imagination/pvr_queue.c",
    "/home/host/kernel-trees/host-build/mainline-6.18/drivers/gpu/drm/imagination/pvr_fw.c",
]

# Matches the exact mangled line with any leading whitespace
PAT = re.compile(r'^(\s*)printk\(KERN_ERR "PVRDBG %s:%d\\n", __func__, __LINE__\); return -EINVAL;$')

total_fixed = 0
for path in FILES:
    with open(path) as f:
        lines = f.readlines()
    out = []
    fixed = 0
    for line in lines:
        m = PAT.match(line.rstrip("\n"))
        if m:
            indent = m.group(1)
            out.append(f"{indent}{{\n")
            out.append(f'{indent}\tprintk(KERN_ERR "PVRDBG %s:%d\\n", __func__, __LINE__);\n')
            out.append(f"{indent}\treturn -EINVAL;\n")
            out.append(f"{indent}}}\n")
            fixed += 1
        else:
            out.append(line)
    if fixed:
        with open(path, "w") as f:
            f.writelines(out)
        print(f"{path}: fixed {fixed} mangled sites")
        total_fixed += fixed
    else:
        print(f"{path}: no mangled sites found")

print(f"TOTAL fixed: {total_fixed}")
