#!/usr/bin/env python3
"""Does sun60iw2_pins[] fit the kcalloc(ngroups*12+4) function array that
sunxi_pinctrl_add_function walks with `while (func->name) func++`?
"""
import re
p = '/home/host/kernel-trees/host-build/mainline-7.3/drivers/pinctrl/sunxi/pinctrl-sun60iw2.c'
s = open(p, errors='replace').read()
i = s.index('sun60iw2_pins[]')
j = s.index('\n};', i)
tbl = s[i:j]
entries = tbl.split('SUNXI_PIN(')[1:]
counts = []
for e in entries:
    n = e.count('SUNXI_FUNCTION')
    counts.append(n)
print(f"entries(SUNXI_PIN)={len(entries)}  max_funcs_per_pin={max(counts)}  min={min(counts)}")
from collections import Counter
print("histogram funcs-per-pin:", sorted(Counter(counts).items()))
over = [(k, c) for k, c in enumerate(counts) if c > 12]
print(f"pins with >12 functions = {len(over)}  -> kcalloc(ngroups*12+4) OVERFLOW if any variant admits them")
if over:
    print("  first offenders (entry idx, nfuncs):", over[:8])
# how many pins are variant-gated (would be skipped -> smaller ngroups)
print("entries containing '.variant' =", tbl.count('.variant'))
print("ngroups would be =", len(entries), " -> kcalloc slots =", len(entries) * 12 + 4,
      "; total add_function calls =", sum(counts))
