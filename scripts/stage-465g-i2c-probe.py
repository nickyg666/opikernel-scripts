#!/usr/bin/env python3
"""Stage one exact 465G production card with the current diagnostic artifacts."""
import hashlib
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/home/host/opikernel')
K = Path('/home/host/kernel-trees/host-build/mainline-7.3')
S = ROOT / 'stage/7.3-stage'
TAB = 'tab@192.168.0.149'
# scp/ssh staging area ON THE TAB. Must NOT be /tmp: the tab reboots and loses
# it mid-investigation (this has happened twice), and /tmp is swept. /var/tmp on
# the tab survives reboot. The host-side equivalent is
# /home/host/opikernel/state/stage, which is a different directory entirely.
REMOTE = '/var/tmp/opiz3w-stage'
IMAGE = 'AUTO'
DTB = 'AUTO'
BOOT = 'AUTO'
# Read-only whole-tree module-release gate, uploaded to the tab and run against
# the CARD's /mnt/sd/lib/modules inside the stage body. It lives with the gate
# logic, not inline here, so the same file is used by the host-side audit, the
# stage script and the ad-hoc probes.
AUDIT = shlex.quote(str(ROOT / 'scripts/audit-kver-prefix.sh'))


def md5(p): return hashlib.md5(p.read_bytes()).hexdigest()
def release_of(image):
    """Kernel release as stamped INTO the Image, never as its filename.

    An Image embeds its own build-time UTS_VERSION, so this is the only
    authority for which lib/modules/<release>/ a board will look in. A dir
    name or a hardcoded constant is a guess that has silently cost us two
    builds (00017 stage dir shipped to a 00018 board).
    """
    import re
    out = subprocess.run(['strings', str(image)], capture_output=True, text=True).stdout
    m = re.search(r'(?m)^(7\.3\.0-rc2-[0-9]+-g[0-9a-f]+(?:-dirty)?)$', out)
    return m.group(1) if m else None
def cp_b_len_of(scr):
    """cp.b <src> <dst> <HEX len> out of a boot.scr, or None.

    cp.b is a FIXED-LENGTH copy: boot.scr hands the length to U-Boot and
    U-Boot copies exactly that many bytes. Nothing else in the pipeline
    computes it, so when the Image grows and boot.scr does not, the kernel is
    silently truncated with no U-Boot error, no serial line and no
    module/vermagic symptom. That is why a card can be perfectly
    kver-consistent and still not boot.
    """
    import re
    m = re.search(rb'cp\.b\s+0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+(0x[0-9a-fA-F]+)',
                  Path(scr).read_bytes())
    return int(m.group(1), 16) if m else None
def make_boot_scr(image, out):
    """(Re)build boot.scr from the Image it must copy. Never hand-edit a
    length that is derived from a build artifact."""
    import re
    n = Path(image).stat().st_size
    src = Path('/home/host/opikernel/pvrgl-work/boot.cmd.live')
    body = re.sub(r'^(cp\.b\s+\S+\s+\S+\s+)0x[0-9a-fA-F]+$',
                  lambda m: m.group(1) + '0x%X' % n, src.read_text(), flags=re.M)
    cmd = Path(out).with_suffix('.cmd')
    cmd.write_text(body)
    subprocess.run(['mkimage', '-A', 'arm', '-T', 'script', '-O', 'linux',
                    '-n', 'OPiZ3W', '-C', 'none', '-d', str(cmd), str(out)],
                   check=True, capture_output=True)
    need(cp_b_len_of(out) == n, 'generated boot.scr cp.b != Image size')
    need(0x40200000 + n <= 0x43999999, 'kernel copy would pass the 32-bit U-Boot ceiling')
    return n
def modinfo_field(ko, field):
    return subprocess.run(['modinfo', '-F', field, str(ko)],
                          capture_output=True, text=True).stdout.strip()
def dep_table(names, ko_dir):
    """Generate modules.dep from the REAL modinfo depends of the set.

    A hand-written dep line is a lie the moment one entry changes: kmod
    loads EVERY prereq listed, so naming a module that is builtin (drm.ko),
    absent, or built for another vermagic (sunxi_rfkill) fails the entire
    line instead of just that entry. Generated == self-consistent by
    construction, because every prereq is either absent from `depends`
    (so nothing is listed) or is one of the files we ship.
    """
    dep = {n: [d for d in modinfo_field(ko_dir / (n + '.ko'), 'depends').split(',') if d]
           for n in names}
    for n, ds in dep.items():
        bad = [d for d in ds if d not in names]
        need(not bad, 'DEP_NOT_STAGED %s needs %s (add it or drop it)' % (n, ','.join(bad)))
    return ''.join('%s.ko: %s\n' % (n, ' '.join(dep[n])) for n in sorted(dep))
def ssh(script, timeout=90):
    return subprocess.run(['sshpass','-p','1','ssh','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=8',TAB,'sh','-s'], input=script, text=True, capture_output=True, timeout=timeout)
def scp(src, dst):
    return subprocess.run(['sshpass','-p','1','scp','-q','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null',str(src),TAB+':'+dst], text=True, capture_output=True, timeout=120)
def need(cond, msg):
    if not cond: raise RuntimeError(msg)
def main():
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    sources={'Image':K/'arch/arm64/boot/Image','sun60i-a733-orangepi-zero3w.dtb':K/'arch/arm64/boot/dts/allwinner/sun60i-a733-orangepi-zero3w.dtb','boot.scr':S/'boot.scr'}
    want={'Image':(IMAGE,(41000000,44000000),bytes.fromhex('1f2003d5')),'sun60i-a733-orangepi-zero3w.dtb':(DTB,(200000,220000),bytes.fromhex('d00dfeed')),'boot.scr':(BOOT,(300,600),None)}
    # Hashes are read from the build tree so the guard cannot rot on every rebuild.
    want={k:(md5(sources[k]) if v[0]=='AUTO' else v[0], v[1], v[2]) for k,v in want.items()}
    globals()['IMAGE']=want['Image'][0]
    globals()['DTB']=want['sun60i-a733-orangepi-zero3w.dtb'][0]
    globals()['BOOT']=want['boot.scr'][0]
    for name,p in sources.items():
        b=p.read_bytes()
        h,w,m=want[name]
        need(md5(p)==h,f'{name} source hash')
        need(w[0]<=len(b)<=w[1] if isinstance(w,tuple) else len(b)==w,f'{name} source size')
        if m is not None:
            need(b[:4]==m,f'{name} source magic')
    for name in ('Image','sun60i-a733-orangepi-zero3w.dtb'):
        src=sources[name]; dst=S/'boot/mainline'/name; bak=dst.with_name(dst.name+'.bak-regdiag-'+stamp); shutil.copy2(dst,bak); shutil.copy2(src,dst); print('HOST_STAGE',dst,md5(dst),'BACKUP',bak)
    # 2026-09-30 CP.B TRUNCATION TRAP: boot.scr's `cp.b 0x41000000 0x40200000
    # <LEN>` length was a hardcoded hex constant that nothing recomputed. The
    # 00018 Image is 44111880 B (0x2A11808) and the staged boot.scr still said
    # 0x2A00000 = 44040192 -- 71688 bytes short. U-Boot copies exactly LEN, so
    # the board gets a silently truncated kernel: no U-Boot error, no serial
    # line, and every kver/vermagic/module check downstream still passes
    # because none of them look at the copy. Generate boot.scr from the Image
    # size every run and assert the invariant on the card after writing.
    imgsz=make_boot_scr(sources['Image'], S/'boot.scr')
    globals()['BOOT']=md5(S/'boot.scr')
    print('HOST_STAGE boot.scr', globals()['BOOT'], 'cp.b=0x%X == Image %d' % (imgsz, imgsz))
    scr=S/'boot.scr'
    need(300<=scr.stat().st_size<=900, 'generated boot.scr size out of range')
    need(cp_b_len_of(scr)==imgsz, 'generated boot.scr cp.b != Image size')
    pre=ssh(r'''set -eu
CAND=; COUNT=0
for d in /dev/sda /dev/sdb /dev/sdc; do
  [ -b "$d" ] || continue
  n=$(lsblk -b -dn -o SIZE "$d" 2>/dev/null | tr -d '[:space:]' || true)
  case "$n" in ''|*[!0-9]*) continue;; esac
  if [ "$n" -ge 450000000000 ]; then CAND="$d"; COUNT=$((COUNT+1)); fi
done
[ "$COUNT" -eq 1 ] || { echo "NO_UNIQUE_465G COUNT=$COUNT"; exit 2; }
[ -b "$CAND"1 ] || { echo "NO_PARTITION $CAND"; exit 2; }
echo "PREFLIGHT_OK CARD=$CAND SIZE=$n"
''')
    need(pre.returncode==0, 'preflight: '+(pre.stdout+pre.stderr).strip()); print(pre.stdout.strip())
    need('PREFLIGHT_OK CARD=' in pre.stdout, 'no preflight')
    card=pre.stdout.split('CARD=',1)[1].split()[0]
    need(ssh('mkdir -p /var/tmp/opiz3w-stage/boot/mainline\n').returncode==0,'upload dir')
    for name in ('Image','sun60i-a733-orangepi-zero3w.dtb','boot.scr'):
        p=sources[name]; r=scp(p,REMOTE+('/boot/mainline/'+name if name!='boot.scr' else '/boot.scr')); need(r.returncode==0,'scp '+name+': '+r.stderr)
    # 2026-09-26: also ship the aic8800 modules. The kernel now has cfg80211
    # built in, so the driver's wiphy_* symbols resolve and these load; without
    # them the board has no Wi-Fi at all.
    # 2026-09-26: aic8800_bsp needs sunxi_wlan_* symbols which live in
    # sunxi_rfkill.ko, so all three must ship together.
    # 2026-09-26: powervr.ko is the GPU driver. CONFIG_DRM_POWERVR=m and the
    # gpu@1800000 node (img,img-bxm-4-64 / img,img-rogue) had no driver bound
    # and /dev/dri did not exist. Ship it plus the rogue firmware.
    # 2026-09-26 STALE-MODULE TRAP: stage/ holds its own copy of each .ko, so a
    # rebuild leaves stage/ stale and the script silently ships the OLD module
    # (seen: tree 8ca627f2 12:16 vs staged ba7a15af 04:32). Fail closed: if the
    # staged copy differs from the freshly built one, refuse rather than deploy
    # the wrong bytes. The operator refreshes stage/ deliberately.
    KDIR = Path('/home/host/kernel-trees/host-build/mainline-7.3')
    # 2026-09-30: sunxi_rfkill REMOVED from the staged set. The tree has
    # CONFIG_AW_RFKILL=y, so sunxi_wlan_set_power/sunxi_wlan_get_bus_index are
    # exported by vmlinux and aic8800_bsp's real `modinfo -F depends` is EMPTY.
    # The staged sunxi_rfkill.ko is a leftover from an earlier =m build and
    # carries an older vermagic, so the hand-written modules.dep line
    # "aic8800_bsp.ko: sunxi_rfkill.ko" makes modprobe fail the whole line on a
    # newer kernel: kmod must load every listed prereq, and it cannot.
    FRESH = {
        'powervr.ko': KDIR/'drivers/gpu/drm/imagination/powervr.ko',
        'drm_kms_helper.ko': KDIR/'drivers/gpu/drm/drm_kms_helper.ko',
        'drm_shmem_helper.ko': KDIR/'drivers/gpu/drm/drm_shmem_helper.ko',
        'drm_gpuvm.ko': KDIR/'drivers/gpu/drm/drm_gpuvm.ko',
        'gpu-sched.ko': KDIR/'drivers/gpu/drm/scheduler/gpu-sched.ko',
        'drm_exec.ko': KDIR/'drivers/gpu/drm/drm_exec.ko',
        'aic8800_bsp.ko': KDIR/'drivers/net/wireless/aic8800/aic8800_bsp/aic8800_bsp.ko',
        'aic8800_fdrv.ko': KDIR/'drivers/net/wireless/aic8800/aic8800_fdrv/aic8800_fdrv.ko',
    }
    for name, built in FRESH.items():
        need(built.is_file(), 'NOT_BUILT %s' % built)
        staged = S/'lib/modules/7.3.0-rc2-dirty'/name
        need(staged.is_file(), 'NOT_STAGED %s (refresh stage/ deliberately)' % staged)
        if md5(built) != md5(staged):
            raise SystemExit(
                'STALE_STAGE %s: build tree %s != stage dir %s\n'
                '  refresh it, e.g. cp %s %s, then re-run'
                % (name, md5(built), md5(staged), built, staged))
    # 2026-09-30 KVER TRAP: the release is whatever the STAGED Image's own bytes
    # say, and every .ko we ship must carry that exact vermagic. Deriving KREL
    # per-file from whatever Image happened to be in stage/ is how a 00017 stage
    # dir got installed onto a 00018 board and every modprobe died on vermagic.
    # One $KVER, asserted, before a single byte is written to the card.
    kver = release_of(S/'boot/mainline/Image')
    need(kver, 'no kernel release in staged Image')
    for name in FRESH:
        vm = modinfo_field(S/'lib/modules/7.3.0-rc2-dirty'/name, 'vermagic')
        need(vm.split() and vm.split()[0] == kver,
             'VERMAGIC_MISMATCH %s: staged .ko=%s staged Image=%s'
             % (name, vm.split()[0] if vm else 'NONE', kver))
    print('KVER_OK %s (all %d staged .ko match)' % (kver, len(FRESH)))
    # 2026-09-26: powervr.ko's real module dependencies. MODULE_INFO(depends,
    # "gpu-sched,drm_gpuvm,drm_shmem_helper,drm_exec") - powervr is modular, so
    # these four MUST be present and loadable. imagination/Kconfig `select`s them
    # from CONFIG_DRM_POWERVR=m, so Kconfig forces them to =m and they can never
    # be built in; shipping them as modules is the only correct arrangement.
    # Without them: "Unknown symbol drm_gpuvm_exec_lock / drm_exec_lock_obj /
    # drm_sched_job_has_dependency" and /dev/dri never appears.
    # Ship EXACTLY the FRESH set. Globbing the stage dir used to pull in
    # leftovers from older kvers (sunxi_rfkill.ko, aic_load_fw.ko) whose
    # vermagic predates the Image, which is how a correct dep table still
    # refused to load on the board.
    # 2026-09-30 UPLOAD-DIR POISON (found by the whole-tree gate, not by a
    # count): {REMOTE}/lib/modules/7.3.0-rc2-dirty is NEVER pruned, so a .ko
    # from an older kver survives there forever. The on-card install loop globs
    # `$d/*.ko`, so every survivor is installed -- sunxi_rfkill.ko@00017 was
    # sitting there and would have tripped STAGED_VERMAGIC_BAD at the LAST step
    # of an otherwise-good run. Wipe the dir before uploading so the upload
    # dir and the card dir can only ever hold the FRESH set.
    need(ssh('rm -rf %s/lib/modules/7.3.0-rc2-dirty && mkdir -p %s/lib/modules/7.3.0-rc2-dirty\n'
             % (REMOTE, REMOTE)).returncode==0, 'reset upload modules dir')
    # Upload the read-only whole-tree gate FIRST, with the payload, so the gate
    # and the bytes it judges ship as one set: a gate that exists only on the
    # host cannot stop a card write, and one uploaded after its own check
    # cannot either.
    need(ssh('mkdir -p %s/usr/local/sbin\n' % REMOTE).returncode==0, 'audit dir')
    need(scp(AUDIT.strip("'"), REMOTE+'/usr/local/sbin/audit-kver-prefix.sh').returncode==0,
         'upload audit-kver-prefix.sh')
    print('AUDIT_GATE_STAGE', md5(Path(AUDIT.strip("'"))))
    for name in sorted(FRESH):
        ko = S/'lib/modules/7.3.0-rc2-dirty'/name
        need(ssh('mkdir -p ' + REMOTE + '/lib/modules/7.3.0-rc2-dirty\n').returncode==0,'upload modules dir')
        r=scp(ko, REMOTE+'/lib/modules/7.3.0-rc2-dirty/'+ko.name)
        need(r.returncode==0, 'scp '+ko.name+': '+r.stderr)
        print('MODULE_STAGE', ko.name, md5(ko))
    # The upload dir must hold EXACTLY the shipped set. audit-kver-prefix.sh
    # cannot answer this: the upload dir is flat (7.3.0-rc2-dirty) and gets
    # renamed to $KVER on the card, so RELEASE_MISSING would fire by design.
    # Assert the set and the vermagics directly -- same discipline, one step
    # earlier, so a bad upload fails here instead of on the card.
    ul = ssh('cd %s/lib/modules/7.3.0-rc2-dirty && '
             'for f in *.ko; do echo "$f $(modinfo -F vermagic $f | cut -d\' \' -f1)"; done\n'
             % REMOTE).stdout.split()
    got = {ul[i]: ul[i+1] for i in range(0, len(ul) - 1, 2) if ul[i].endswith('.ko')}
    need(sorted(got) == sorted(FRESH), 'UPLOAD_DIR_NOT_EXACT has %s want %s'
         % (sorted(got), sorted(FRESH)))
    badvm = {n: v for n, v in got.items() if v != kver}
    need(not badvm, 'UPLOAD_DIR_VERMAGIC %s' % badvm)
    print('UPLOAD_DIR_OK %d .ko, all %s' % (len(got), kver))
    # 2026-09-26: aic8800 firmware. aic_bsp_8800d80.c requests these names
    # (per the boot log, suffixed): fmacfw_8800d80_u02.bin, fw_patch_8800d80_u02.bin,
    # fw_patch_table_8800d80_u02.bin, fw_adid_8800d80_u02.bin, lmacfw_rf_8800d80_u02.bin.
    # The vendor SDK ships them with a _u02 suffix, so without suffixed
    # copies every request_firmware() failed: the chip never loaded firmware,
    # reported an empty "Firmware Version:", and the first IPC command
    # (MM_SET_STACK_START_REQ) timed out and latched cmd_mgr CRASHED.
    #
    # 2026-09-30 ROOT CAUSE FIX: this loop read S/'fw/aic8800d80' -- the full
    # 50-file vendor variant soup -- and scp'd EVERY entry to the card under
    # its own name. The bare path was then overwritten with variant bytes
    # (fmacfw 358072 instead of 324720), because kernel request_firmware()
    # does exact-name lookup only and simply reads whatever sits there.
    # Source from lib/firmware/aic8800d80 instead: that dir holds exactly the
    # requested names, byte-verified against the vendor SDK, so a variant can
    # never be staged. Fail closed below on both counts.
    aicfw = S / 'lib/firmware/aic8800d80'
    if aicfw.is_dir():
        need(ssh('mkdir -p ' + REMOTE + '/lib/firmware/aic8800d80\n').returncode==0,
             'aic fw dir')
        staged = []
        for blob in sorted(aicfw.iterdir()):
            if '.aic8800-' in blob.name:
                need(False, 'VARIANT BLOB IN CANONICAL SET: ' + blob.name)
            if scp(blob, REMOTE + '/lib/firmware/aic8800d80/' + blob.name).returncode == 0:
                print('AICFW_STAGE', blob.name, md5(blob))
                staged.append(blob)
            else:
                need(False, 'aicfw ' + blob.name)
        # Fail closed on content, not just presence: a wrong-size blob at a
        # bare path is precisely the Sep-06 fault and is invisible to a name
        # check. Sizes are the canonical SDK values.
        for req, want_sz in (('fmacfw_8800d80_u02.bin', 324720),
                             ('fw_patch_8800d80_u02.bin', 25300),
                             ('fw_patch_table_8800d80_u02.bin', 984),
                             ('fw_adid_8800d80_u02.bin', 1708)):
            hit = [b for b in staged if b.name == req]
            need(bool(hit) and hit[0].stat().st_size == want_sz,
                 'CANON-SIZE %s want %d got %s'
                 % (req, want_sz, hit[0].stat().st_size if hit else 'ABSENT'))
            print('AICFW_CANON_OK', req, want_sz)

    # 2026-09-26: upload the module index too. It was previously only installed
    # on the card from {REMOTE}, but never scp'd there, so the card
    # kept a STALE modules.dep and modprobe could not resolve powervr's
    # drm_gpuvm/drm_exec/gpu-sched/drm_shmem_helper dependencies.
    # GENERATE the dep table from the shipped set's own `depends` instead of
    # copying the stale hand-written one sitting in stage/. modules.dep has
    # shipped naming drm.ko (builtin, no file) and sunxi_rfkill.ko (older
    # vermagic) as prereqs, and kmod fails the WHOLE line on an unloadable
    # prereq rather than skipping it. modules.load is generated too, in
    # reverse dependency order, and only from modules we actually ship.
    ko_dir = S/'lib/modules/7.3.0-rc2-dirty'
    names = sorted(n[:-3] for n in FRESH)
    dep_txt = dep_table(names, ko_dir)
    need(('powervr.ko:' in dep_txt) and ('drm_kms_helper.ko' in dep_txt),
         'generated modules.dep is missing powervr or drm_kms_helper')
    need('drm.ko' not in dep_txt.replace('drm_kms_helper.ko', ''),
         'generated modules.dep still names builtin drm.ko')
    # 2026-09-30 DEP-INTEGRITY GATE. depmod SILENTLY DROPS a prerequisite it
    # cannot find on disk: on the 465G card drm_shmem_helper.ko declares
    # depends=drm_kms_helper, drm_kms_helper.ko was missing from the dir, and
    # depmod emitted the line BARE ("drm_shmem_helper.ko:") instead of failing.
    # The card then booted with a table that reads self-consistent but cannot
    # resolve powervr. So assert the chain is CLOSED on the table we generate:
    # every prereq we record must exist as a file in the staged set, and every
    # declared `depends` entry must survive into the table.
    declared = {}
    for line in dep_txt.splitlines():
        if ':' not in line:
            continue
        mod, _, rest = line.partition(':')
        declared[mod.strip()] = rest.split()
    for name in FRESH:
        vm_dep = modinfo_field(ko_dir/name, 'depends')
        wants = [d for d in vm_dep.split(',') if d.strip()]
        need(name in declared, 'DEP_MISSING %s has no modules.dep line' % name)
        got = declared[name]
        need(len(got) >= len(wants),
             'DEP_TRUNCATED %s: .modinfo declares [%s] but modules.dep records [%s] -- '
             'a prereq .ko is absent from the staged set'
             % (name, ','.join(wants), ' '.join(got)))
        for prereq in got:
            # dep_table emits BARE module names (modinfo's `depends` form), so
            # the file on disk is <prereq>.ko. Checking prereq as-is would make
            # every prereq look dangling and refuse a perfectly good set.
            need((ko_dir/(prereq + '.ko')).is_file(),
                 'DEP_DANGLING %s needs %s but %s.ko is not staged'
                 % (name, prereq, prereq))
    print('DEP_OK %s (%d modules, chain closed)' % (kver, len(FRESH)))
    md = S/'lib/modules/modules.dep.generated'
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(dep_txt)
    load_txt = ''.join(n + '\n' for n in reversed(names))
    ml = S/'lib/modules/modules.load.generated'
    ml.write_text(load_txt)
    for idxname, src in (('modules.dep', md), ('modules.load', ml),
                         ('modules.alias', ko_dir/'modules.alias'),
                         ('modules.softdep', ko_dir/'modules.softdep'),
                         # 2026-09-30: these two were NEVER in the upload list,
                         # so no card kver dir ever received them. sunxi_rfkill is
                         # CONFIG_AW_RFKILL=y and drm is CONFIG_DRM=y: both live in
                         # the Image, so `modprobe <name>` can only resolve through
                         # modules.builtin. Without it kmod answers FATAL "not
                         # found" for every builtin name in the autoload list.
                         ('modules.builtin', ko_dir/'modules.builtin'),
                         ('modules.builtin.modinfo', ko_dir/'modules.builtin.modinfo')):
        if not src.is_file():
            print('MODULE_INDEX_SKIP', idxname, '(absent)')
            continue
        need(ssh('mkdir -p ' + REMOTE + '/lib/modules/7.3.0-rc2-dirty\n').returncode==0,
             'upload modules dir')
        r=scp(src, REMOTE+'/lib/modules/7.3.0-rc2-dirty/'+idxname)
        need(r.returncode==0, 'scp '+idxname+': '+r.stderr)
        print('MODULE_INDEX', idxname, md5(src))
    print('GENERATED_DEP_TABLE\n' + dep_txt.rstrip())
    # 2026-09-26: the first-boot helper (depmod + modules-load.d + load now +
    # mask wait-online). Without it the board comes up with only `lo` because
    # nothing autoloads the modules, and the getty stalls 80s on
    # networkd-wait-online despite this board having no Ethernet port at all.
    fb = S/'opiz3w-firstboot.sh'
    if fb.is_file():
        need(ssh('mkdir -p ' + REMOTE + '/usr/local/sbin\n').returncode==0, 'firstboot dir')
        r=scp(fb, REMOTE+'/usr/local/sbin/opiz3w-firstboot.sh')
        need(r.returncode==0, 'scp firstboot: '+r.stderr)
        print('FIRSTBOOT', fb.name, md5(fb))
    # 2026-09-26: PowerVR rogue firmware; powervr.ko requests
    # powervr/rogue_36.5x.104.*_v1.fw (modinfo -F firmware).
    pwfw = S / 'lib/firmware/powervr'
    if pwfw.is_dir():
        need(ssh('mkdir -p ' + REMOTE + '/lib/firmware/powervr\n').returncode == 0, 'pwfw dir')
        for blob in sorted(pwfw.iterdir()):
            need(scp(blob, REMOTE + '/lib/firmware/powervr/' + blob.name).returncode == 0,
                 'scp ' + blob.name)
            print('PVRFW_STAGE', blob.name, md5(blob))
    up=ssh(f'md5sum {REMOTE}/boot.scr {REMOTE}/boot/mainline/Image '
          f'{REMOTE}/boot/mainline/sun60i-a733-orangepi-zero3w.dtb\n')
    need(up.returncode==0,'upload hash'); print(up.stdout.strip()); need(all(x in up.stdout for x in (BOOT,IMAGE,DTB)),'upload hash mismatch')
    body=f'''set -eux
# Kernel release that the staged Image will actually boot as. Read it from the
# Image itself instead of hardcoding: an Image keeps its build-time
# UTS_VERSION stamp, so this changes on every rebuild.
# 2026-09-26: the -dirty suffix only appears when the tree is dirty, so a
# clean build produced no match and `set -e` aborted the whole staged run
# with an empty KREL. Match the release with or without the suffix.
KVER='{kver}'
d='{REMOTE}/lib/modules/7.3.0-rc2-dirty'
echo "opiz3w-stage: installing modules for KVER=$KVER (asserted from Image bytes)"
# Fail closed if the Image that was uploaded does NOT carry the release whose
# .ko we shipped. This is the 00017->00018 trap: KREL used to be re-derived
# from whatever Image sat in stage/, so a stale Image silently installed a
# wrong-kver lib/modules dir and every modprobe died on vermagic.
IMREL="$(strings {REMOTE}/boot/mainline/Image 2>/dev/null \
        | grep -m1 -E '^7[.]3[.]0-rc2-[0-9]+-g[0-9a-f]+(-dirty)?$')"
[ "$IMREL" = "$KVER" ] || {{ echo "KVER_IMAGE_MISMATCH uploaded=$IMREL shipped=$KVER"; exit 5; }}
if findmnt -n /mnt/sd >/dev/null 2>&1; then umount /mnt/sd; fi
mount {shlex.quote(card+'1')} /mnt/sd
trap 'umount /mnt/sd >/dev/null 2>&1 || true' EXIT
# 2026-09-27: /mnt/sd on the tab is frequently stale-mounted to the tab's own
# vfat EFI partition, and that shows "EFI" regardless of what is mounted over it.
# Verify we really landed on this card's ext4 partition before writing anything.
MOUNTED_SRC=$(findmnt -n -o SOURCE /mnt/sd)
case "$MOUNTED_SRC" in
  {shlex.quote(card+'1')}) ;;
  *) echo "WRONG_MOUNT: /mnt/sd is $MOUNTED_SRC, expected {shlex.quote(card+'1')}"; exit 4 ;;
esac
[ "$(findmnt -n -o FSTYPE /mnt/sd)" = "ext4" ] || {{ echo "WRONG_FSTYPE: $(findmnt -n -o FSTYPE /mnt/sd)"; exit 4; }}
[ -f /mnt/sd/boot.scr ] && [ -f /mnt/sd/boot/mainline/Image ] && [ -f /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb ]
cp -a /mnt/sd/boot.scr /mnt/sd/boot.scr.bak-regdiag-{stamp}
cp -a /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/Image.bak-regdiag-{stamp}
cp -a /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb.bak-regdiag-{stamp}
install -m 0644 {REMOTE}/boot.scr /mnt/sd/boot.scr
install -m 0644 {REMOTE}/boot/mainline/Image /mnt/sd/boot/mainline/Image
install -m 0644 {REMOTE}/boot/mainline/sun60i-a733-orangepi-zero3w.dtb /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
# 2026-09-30: assert the cp.b invariant ON THE CARD. This is the only place
# that can see the bytes that will actually be copied -- the host checks
# proved the staged pair, a stale pair on the card would boot a truncated
# kernel with every other check still green.
CPSB="$(strings /mnt/sd/boot.scr | grep -oE 'cp[.]b [^ ]+ [^ ]+ 0x[0-9a-fA-F]+' | awk '{{print $4}}')"
CPSZ="$(stat -c %s /mnt/sd/boot/mainline/Image)"
CPSZ_HEX="$(printf '0x%X' "$CPSZ")"
if [ "$CPSB" != "$CPSZ_HEX" ]; then
  echo "CPB_TRUNCATION boot.scr copies $CPSB but Image is $CPSZ ($CPSZ_HEX) -- kernel would be truncated"; exit 6
fi
echo "opiz3w-stage: CPB_OK boot.scr copies $CPSB == Image $CPSZ"
# 2026-09-30: install ONLY the shipped set, ONLY into $KVER. Installing into
# a second, hardcoded dir is what let a stale-kver tree masquerade as the live
# one; modprobe reads /lib/modules/$(uname -r), so one correct dir is enough.
rm -rf /mnt/sd/lib/modules/7.3.0-rc2-dirty
for f in {REMOTE}/lib/modules/7.3.0-rc2-dirty/*.ko; do
  [ -f "$f" ] || continue
  mkdir -p "/mnt/sd/lib/modules/$KVER"; install -m 0644 "$f" "/mnt/sd/lib/modules/$KVER/"
done
# Assert every shipped .ko really landed under $KVER with the right vermagic.
# modprobe looks in /lib/modules/$(uname -r) ONLY, so a file that exists
# elsewhere on the card is invisible and reads as "Module not found".
NV=0; NBAD=0
for f in /mnt/sd/lib/modules/$KVER/*.ko; do
  [ -f "$f" ] || continue
  NV=$((NV+1))
  vm="$(modinfo -F vermagic "$f" 2>/dev/null | cut -d' ' -f1)"
  [ "$vm" = "$KVER" ] || {{ echo "STAGED_VERMAGIC_BAD $f has=$vm want=$KVER"; NBAD=$((NBAD+1)); }}
done
echo "opiz3w-stage: staged $NV modules into $KVER, $NBAD vermagic mismatches"
[ "$NV" -ge 8 ] || {{ echo "TOO_FEW_MODULES $NV"; exit 6; }}
[ "$NBAD" -eq 0 ] || exit 6
# 2026-09-30 KVER-PREFIX TRAP (whole-tree check, PA's sibling ask). Everything
# above only looks at lib/modules/$KVER. modprobe reads $(uname -r) and NOTHING
# else, so every other dir on the card is inert until the day uname changes.
# The 465G card carried 16 release dirs, 9 with .ko whose vermagic did not match
# their own dir, plus a second 7.3.0-rc2-00018-g<othercommit> that sorts ADJACENT
# to the live one -- any `7.3.0-rc2-00018-*` glob silently mixes two commits.
# Re-stamping into a poisoned neighbour is exactly what must not happen, so
# this is a hard gate, not a note. Read-only: dir names + modinfo only.
LIVE=$KVER sh {REMOTE}/usr/local/sbin/audit-kver-prefix.sh /mnt/sd/lib/modules || {{ echo "KVER_PREFIX_FAIL on-card (see findings above) -- refusing to continue"; exit 7; }}
# 2026-09-26: ship the module index. Without modules.dep, `modprobe <mod>`
# fails with "Module not found" even though the .ko is present, and nothing
# auto-loads at boot.
# 2026-09-30: the generated table is derived from the real `depends` of the
# shipped set, so it cannot name a builtin (drm.ko) or an absent module
# (sunxi_rfkill) the way the old hand-written one did. kmod fails the WHOLE
# line on an unloadable prereq, so one bad entry killed the entire module.
for f in "$d"/modules.dep "$d"/modules.alias "$d"/modules.softdep "$d"/modules.load \
           "$d"/modules.builtin "$d"/modules.builtin.modinfo; do
  # 2026-09-30: modules.builtin was MISSING here, so a builtin-only name
  # (sunxi_rfkill with CONFIG_AW_RFKILL=y) could never resolve on the card.
  [ -f "$f" ] || continue
  install -m 0644 "$f" "/mnt/sd/lib/modules/$KVER/"
done
if [ -d {REMOTE}/lib/firmware/aic8800d80 ]; then
  mkdir -p /mnt/sd/lib/firmware/aic8800d80
  install -m 0644 {REMOTE}/lib/firmware/aic8800d80/* /mnt/sd/lib/firmware/aic8800d80/
fi
if [ -d {REMOTE}/lib/firmware/powervr ]; then
  mkdir -p /mnt/sd/lib/firmware/powervr
  install -m 0644 {REMOTE}/lib/firmware/powervr/* /mnt/sd/lib/firmware/powervr/
fi
# 2026-09-26: install the first-boot helper and make it a systemd unit so module
# autoload + depmod happen on every boot without manual insmod.
if [ -f {REMOTE}/usr/local/sbin/opiz3w-firstboot.sh ]; then
  mkdir -p /mnt/sd/usr/local/sbin
  install -m 0755 {REMOTE}/usr/local/sbin/opiz3w-firstboot.sh /mnt/sd/usr/local/sbin/
  mkdir -p /mnt/sd/etc/systemd/system
  cat > /mnt/sd/etc/systemd/system/opiz3w-modules.service << 'UNIT'
[Unit]
Description=opiz3w module autoload (aic8800 WiFi + PowerVR GPU)
After=systemd-modules-load.service local-fs.target
Wants=network.target
[Service]
Type=oneshot
RemainAfterExit=yes
# 2026-09-26: aicbsp_init can block indefinitely while the SDIO chip is being
# brought up. Without a timeout that hung the whole boot at 18s and the serial
# getty never came up, making the board look dead. Bound it hard, and keep it
# out of the boot-critical path (After=, never Before=network.target).
TimeoutStartSec=20
TimeoutStopSec=10
ExecStart=/usr/local/sbin/opiz3w-firstboot.sh
[Install]
WantedBy=multi-user.target
UNIT
  mkdir -p /mnt/sd/etc/systemd/system/multi-user.target.wants
  # 2026-09-26: do NOT enable the autoload unit by default. aic8800_bsp can
  # block indefinitely during insmod, which froze the boot at ~17.9s with no
  # getty and no way to talk to the board. Modules are loaded by hand (or by
  # `systemctl start opiz3w-modules`) once we know the load is safe.
  # ln -sf /etc/systemd/system/opiz3w-modules.service \
  #   /mnt/sd/etc/systemd/system/multi-user.target.wants/opiz3w-modules.service
  rm -f /mnt/sd/etc/systemd/system/multi-user.target.wants/opiz3w-modules.service
  rm -f /mnt/sd/etc/systemd/system/multi-user.target.wants/systemd-networkd-wait-online.service
  mkdir -p /mnt/sd/etc/systemd/system
  # 2026-09-26: `ln -sf /dev/null ...` aborted the whole staged run with
  # "mkdir: Permission denied" under `set -eu`, because the sudo -S password
  # had already been consumed and the symlink was created unprivileged.
  # Write a real unit file instead - it masks just as well and needs no
  # elevated symlink creation.
  cat > /mnt/sd/etc/systemd/system/systemd-networkd-wait-online.service << 'MASKUNIT'
[Unit]
Description=disabled on opiz3w: this board has no physical Ethernet

[Service]
Type=oneshot
ExecStart=/bin/true
ExecStop=/bin/true
RemainAfterExit=yes
MASKUNIT
fi
sync
md5sum /mnt/sd/boot.scr /mnt/sd/boot/mainline/Image /mnt/sd/boot/mainline/sun60i-a733-orangepi-zero3w.dtb
sync
'''
    mut=ssh("printf '%s\\n' 1 | sudo -S -p '' sh -c "+shlex.quote(body))
    if mut.returncode != 0:
        print('MUTATION_STDOUT:\n'+mut.stdout)
        print('MUTATION_STDERR:\n'+mut.stderr)
        raise SystemExit('mutation failed rc=%d' % mut.returncode)
    print(mut.stdout.strip())
    need(all(x in mut.stdout for x in (BOOT,IMAGE,DTB)),'card hash mismatch')
    print('STAGED_OK',stamp)
if __name__=='__main__':
    try: main()
    except Exception as e: print('STAGING_ABORT',e,file=sys.stderr); raise
