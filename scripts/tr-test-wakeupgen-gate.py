#!/usr/bin/env python3
"""TR 20260920-2005: prove the wakeupgen gate both ways on real bytes.
positive = KDIR Image (port landed); negative = stage/7.3-stage/Image (pre-port, the one
that was on the card during the failed boot)."""
import importlib.util, sys
spec = importlib.util.spec_from_file_location(
    "pub", "/home/host/opikernel/scripts/publish-7.3-artifacts.py")
m = importlib.util.module_from_spec(spec)
sys.argv = ["pub"]
spec.loader.exec_module(m)
cases = [
    ("POSITIVE KDIR", "/home/host/kernel-trees/host-build/mainline-7.3/arch/arm64/boot/Image"),
    ("NEGATIVE stage/pre-port", "/home/host/opikernel/stage/7.3-stage/Image"),
]
for name, path in cases:
    m.IMAGE = path
    ok, reason, facts = m.gate(force=False, min_age=0)
    f = facts.get("irqchip_wakeupgen", {})
    print(f"{name}: gate_ok={ok} in_image={f.get('in_image')} in_modules={f.get('in_modules')}")
    print(f"   reason: {reason[:160]}")
