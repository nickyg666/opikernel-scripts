#!/usr/bin/env python3
"""Replace the self-killing `pkill -f ...ttyACM0...` shotgun with the PID-aware
claimer (scripts/claim-serial-port.sh).

WHY THIS MATTERS: `pkill -f <pattern>` matches the FULL command line. A Hermes/agent
wraps commands as `bash -c "... pkill -f 'cat /dev/ttyACM0' ..."`, so that wrapper's
own cmdline contains the pattern and the pkill SIGTERMs the caller. Worst cases
in-repo: `pkill -f 'uboot'` inside uboot_full_fix.py (its own argv contains "uboot")
and `pkill -f 'uboot_coldboot'` inside uboot_coldboot.py — both kill themselves on
every run. This is the root cause of "the agent died mid-run" / "capture stopped".

Usage: pkill-fix.py [--apply]      (default is dry-run)
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

APPLY = "--apply" in sys.argv
STAMP = "bak-pkillfix-20260918"
CLAIMER = "/home/host/opikernel/scripts/claim-serial-port.sh"
CLAIM = f"sudo {CLAIMER} >/dev/null 2>&1"

ROOTS = ["/home/host/opikernel/pvrgl-work", "/home/host/opikernel/scripts"]

# Any pkill whose pattern can match a serial reader. Order matters: the widest
# "quoted shell command" rules run first so the inner detail is consumed.
PK = r"""pkill\s+-9?\s*-f\s+['"]?[^'"]*ttyACM0[^'"]*['"]?"""

RULES = [
    # --- python: sh("sudo pkill ...") ; sh("sudo pkill ...")  -----------------
    (re.compile(r"""sh\("sudo pkill -f 'serial_keeper\.sh'"\);\s*sh\("sudo pkill -f 'cat /dev/ttyACM0'"\)"""),
     f'sh("sudo {CLAIMER}")'),
    (re.compile(r"""sh\(\s*"[^"]*pkill[^"]*ttyACM0[^"]*"\s*\)"""),
     f'sh("sudo {CLAIMER} >/dev/null 2>&1")'),
    # --- python: subprocess.run("...pkill...", shell=True)  ------------------
    (re.compile(r"""subprocess\.run\(\s*"[^"]*pkill[^"]*ttyACM0[^"]*"\s*,\s*shell=True\s*\)"""),
     f'subprocess.run("{CLAIM}", shell=True)'),
    # --- python: os.system("...pkill...")  ----------------------------------
    (re.compile(r"""os\.system\(\s*"[^"]*pkill[^"]*ttyACM0[^"]*"\s*\)"""),
     f'os.system("{CLAIM}")'),
    # --- python: subprocess.run(['pkill','-f','cat /dev/ttyACM0'])  ---------
    (re.compile(r"""subprocess\.run\(\s*\[\s*['"]pkill['"]\s*,\s*['"]-[^'"]*['"]\s*,\s*['"][^'"]*ttyACM0[^'"]*['"]\s*\](\s*,\s*capture_output=True)?\s*\)"""),
     f'subprocess.run("{CLAIM}", shell=True)'),
    # --- bash: leading pkill line (any quoting), optional redirect/|| true ---
    (re.compile(r"""^(\s*)(?:sudo\s+)?pkill\s+-9?\s*-f\s+["'][^"']*ttyACM0[^"']*["'][^\n]*$"""),
     rf'\1{CLAIM}'),
    # --- anything else still holding 'pkill' + ttyACM0 ----------------------
    (re.compile(r"""(?:sudo\s+)?pkill[^\n]*ttyACM0[^\n]*"""),
     CLAIM),
]

SKIP = {"kill-serial-runaways.py", "claim-serial-port.sh", "pkill-fix.py", "agent-watchdog.sh"}


def is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("#") or s.startswith('"""') or s.startswith("'''")


changed, unhandled, comments, broken = [], [], 0, []
for root in ROOTS:
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or p.name in SKIP or p.suffix not in (".py", ".sh", ".bash"):
            continue
        try:
            txt = p.read_text(errors="strict")
        except Exception:
            continue
        if "pkill" not in txt or "ttyACM0" not in txt:
            continue
        out, hit = [], 0
        for line in txt.splitlines(keepends=True):
            if "pkill" in line and "ttyACM0" in line:
                if is_comment(line):
                    comments += 1
                    out.append(line)
                    continue
                new = line
                for rx, rep in RULES:
                    new2 = rx.sub(rep, new)
                    if new2 != new:
                        new = new2
                        hit += 1
                        break
                else:
                    unhandled.append((str(p), line.rstrip()))
                out.append(new)
            else:
                out.append(line)
        if hit:
            newsrc = "".join(out)
            # SAFETY NET: never write a file that no longer parses. A bad rewrite
            # here silently breaks 100+ ops scripts, so validate before committing.
            if p.suffix == ".py":
                import py_compile, tempfile
                try:
                    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
                        tf.write(newsrc)
                        tmp = tf.name
                    py_compile.compile(tmp, cfile=tmp + "c", doraise=True)
                    os.unlink(tmp + "c")
                except Exception as e:
                    broken.append((str(p), str(e)[:160]))
                    os.unlink(tmp)
                    continue
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
            elif p.suffix in (".sh", ".bash"):
                import tempfile
                with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as tf:
                    tf.write(newsrc)
                    tmp = tf.name
                r = subprocess.run(["bash", "-n", tmp], capture_output=True, text=True)
                os.unlink(tmp)
                if r.returncode != 0:
                    broken.append((str(p), (r.stderr or "").strip()[:160]))
                    continue
            changed.append((str(p), hit))
            if APPLY:
                bak = p.with_name(p.name + "." + STAMP)
                if not bak.exists():
                    shutil.copy2(p, bak)
                p.write_text(newsrc)

print(f"mode={'APPLY' if APPLY else 'DRY-RUN'}")
print(f"files changed: {len(changed)}   lines rewritten: {sum(n for _, n in changed)}")
for f, n in changed:
    print(f"  {n:2d}  {f}")
print(f"\ncomment lines skipped: {comments}")
if broken:
    print(f"\nSKIPPED — rewrite would not parse ({len(broken)}):")
    for f, e in broken:
        print(f"  {f}\n     {e}")
if unhandled:
    print(f"\nUNHANDLED ({len(unhandled)}):")
    for f, l in unhandled:
        print(f"  {f}\n     {l}")
