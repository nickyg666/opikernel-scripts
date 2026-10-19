#!/usr/bin/env python3
"""TR 20260920-2005: mark the pre-port published build as superseded so nobody installs a
kernel that cannot probe the wakeupgen irqchip. Reuses the publisher's own token() so no
credential is ever printed or duplicated."""
import importlib.util, os, sys, subprocess

spec = importlib.util.spec_from_file_location(
    "pub", "/home/host/opikernel/scripts/publish-7.3-artifacts.py")
m = importlib.util.module_from_spec(spec)
sys.argv = ["pub"]
spec.loader.exec_module(m)

REPO = m.REPO_DIR
BAD = "20260920-143001-3056d664"
GOOD = "20260920-231110-eff8af11"
MARK = "SUPERSEDED.md"
body = f"""# SUPERSEDED — do not install

This build's `Image.xz` decompresses to 41,666,568 B, magic `1f2003d5` (looks perfect) and
contains **zero** occurrences of the `sunxi-wakeupgen` driver match string.

The DTB shipped in every 7.3 bundle declares `/interrupt-controller@0` compatible
`allwinner,sunxi-wakeupgen`. A kernel without that driver cannot probe the irqchip, so
`pinctrl@2000000` — and every mmc/SDIO/pinmux consumer deferring on it — fails with `-517`
forever. That is exactly the 09-20 boot failure (no `mmc0` pins, no root device).

Verified by byte-reading both published Images:
- `{BAD}` → `strings -a Image | grep -c sunxi-wakeupgen` = **0** (pre-port)
- `{GOOD}` → same command = **1** (port landed; `System.map`: `t wakeupgen_init`,
  `d __of_table_sunxi_wakeupgen`)

Use `{GOOD}` (this repo's `LATEST`). `scripts/publish-7.3-artifacts.py` now hard-fails this
case (gate step 8, `irqchip_wakeupgen_facts()`), so it cannot recur.
"""
path = os.path.join(REPO, "builds", BAD, MARK)
open(path, "w").write(body)
print("wrote", path, os.path.getsize(path), "B")

def git(*a, **kw):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, **kw)

r = git("add", "-A"); print("add rc", r.returncode, r.stderr.strip()[:120])
r = git("-c", "user.email=tr@opikernel.local", "-c", "user.name=TelegramRunner",
        "commit", "-q", "-m", f"mark {BAD} SUPERSEDED: no sunxi-wakeupgen driver in Image "
                              f"(pinctrl -517 boot gate); use {GOOD}")
print("commit rc", r.returncode, (r.stdout + r.stderr).strip()[:200])
local = git("rev-parse", "HEAD").stdout.strip()
tk = m.token()
url = f"https://nickyg666:{tk}@{m.REMOTE}"
r = subprocess.run(["git", "-C", REPO, "push", "-q", url, "HEAD:refs/heads/main"],
                   capture_output=True, text=True)
print("push rc", r.returncode, r.stderr.replace(tk, "***")[:200] if r.stderr else "")
ls = subprocess.run(["git", "-C", REPO, "ls-remote", url, "refs/heads/main"],
                    capture_output=True, text=True)
remote_sha = ls.stdout.split()[0] if ls.stdout.split() else "(none)"
print("local HEAD ", local)
print("remote HEAD", remote_sha)
print("MATCH:", local == remote_sha)
