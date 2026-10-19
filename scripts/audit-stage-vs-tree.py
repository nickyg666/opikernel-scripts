#!/usr/bin/env python3
"""Audit stage/7.3-stage against the live build tree before any card write.

Answers three questions that have each silently cost us a boot:
  1. Does stage/ hold the Image the build tree currently produces? (release skew)
  2. Does every .ko in stage/ match the freshly built one? (stale bytes)
  3. Is every .ko stage/ ships still a MODULE? (built-in => can never load)

Exits 1 on any finding. Read-only; the refresh is a separate deliberate step.
"""
import re
import subprocess
import sys
from pathlib import Path

KDIR = Path('/home/host/kernel-trees/host-build/mainline-7.3')
STAGE = Path('/home/host/opikernel/stage/7.3-stage')
MODDIR = STAGE / 'lib/modules/7.3.0-rc2-dirty'


def uts_release(image):
    try:
        blob = image.read_bytes()
    except OSError:
        return None
    m = re.search(rb'7\.3\.0-rc2-[0-9]+-g[0-9a-f]+(?:-dirty)?', blob)
    return m.group(0).decode() if m else None


def md5(path):
    return subprocess.run(['md5sum', str(path)], capture_output=True,
                          text=True).stdout.split()[0]


def main():
    bad = []
    tree_img = KDIR / 'arch/arm64/boot/Image'
    stage_img = STAGE / 'boot/mainline/Image'
    t_rel, s_rel = uts_release(tree_img), uts_release(stage_img)
    print('tree  Image %s' % (t_rel or 'NO-UTS'))
    print('stage Image %s' % (s_rel or 'NO-UTS'))
    if t_rel and s_rel and t_rel != s_rel:
        bad.append('RELEASE_SKEW stage/ holds %s, tree builds %s -- '
                   'every .ko and modules.dep in stage/ is for the wrong '
                   'uname -r' % (s_rel, t_rel))

    # One traversal for the built .ko inventory.
    built = {p.name: p for p in KDIR.rglob('*.ko')}
    builtin = set()
    bi = KDIR / 'modules.builtin'
    if bi.is_file():
        builtin = {ln.strip().rsplit('/', 1)[-1] for ln in bi.read_text().splitlines()}

    print('\n%-24s %-18s %-18s %s' % ('KO', 'stage', 'tree', 'verdict'))
    for ko in sorted(MODDIR.glob('*.ko')):
        if '.bak' in ko.name:
            continue
        t = built.get(ko.name)
        s = md5(ko)
        if t is None:
            if ko.name in builtin:
                print('%-24s %-18s %-18s %s' % (ko.name, s[:16], 'BUILT-IN', 'DEAD'))
                bad.append('BUILT_IN %s is in modules.builtin (=y) -- a module '
                           'copy can never load on this kernel' % ko.name)
            else:
                print('%-24s %-18s %-18s %s' % (ko.name, s[:16], 'ABSENT', 'UNKNOWN'))
                bad.append('UNKNOWN %s not built and not built-in' % ko.name)
            continue
        tm = md5(t)
        same = (tm == s)
        vm = subprocess.run(['modinfo', '-F', 'vermagic', str(ko)],
                            capture_output=True, text=True).stdout.split()[0]
        good = vm == t_rel
        verdict = 'ok' if same and good else ('STALE_BYTES' if not same else 'VERMAGIC')
        print('%-24s %-18s %-18s %s  (vm=%s)' % (ko.name, s[:16], tm[:16], verdict, vm))
        if not same:
            bad.append('STALE_STAGE %s stage=%s tree=%s' % (ko.name, s[:16], tm[:16]))
        if not good:
            bad.append('VERMAGIC %s is %s, tree release is %s'
                       % (ko.name, vm, t_rel))

    if bad:
        print('\n=== %d FINDING(S) ===' % len(bad))
        for b in bad:
            print(' * ' + b)
        return 1
    print('\nSTAGE_AUDIT_CLEAN')
    return 0


if __name__ == '__main__':
    sys.exit(main())
