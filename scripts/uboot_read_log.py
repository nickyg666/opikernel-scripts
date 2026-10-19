#!/usr/bin/env python3
"""Read the rescue log and extract the important parts."""
import sys, os

LOG = "/home/host/pvrgl-work/uboot_rescue.log"
if len(sys.argv) > 1:
    LOG = sys.argv[1]

with open(LOG, 'rb') as f:
    content = f.read().decode('utf-8', errors='replace')

print(f"=== {LOG} ({len(content)} chars) ===\n")
print(content)
