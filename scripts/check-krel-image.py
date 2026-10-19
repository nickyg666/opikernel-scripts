#!/usr/bin/env python3
"""Read the UTS release string stamped into an arm64 Image and report it.

Used by the staging scripts to pick the /lib/modules/<release> dir instead of
guessing. An Image keeps its build-time LINUX_VERSION, so this changes on every
rebuild; hardcoding '7.3.0-rc2-dirty' is what put 00018 modules on a 00017 dir.
"""
import re
import sys


def uts_release(image):
    with open(image, 'rb') as fh:
        blob = fh.read()
    m = re.search(rb'7\.3\.0-rc2-[0-9]+-g[0-9a-f]+(?:-dirty)?', blob)
    return m.group(0).decode() if m else None


if __name__ == '__main__':
    for path in sys.argv[1:]:
        rel = uts_release(path)
        print('%-62s %s' % (path, rel or 'NO-UTS-STRING'))
