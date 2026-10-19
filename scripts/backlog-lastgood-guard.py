#!/usr/bin/env python3
"""PA: last-good guard for the canonical queue (agentic-pool/BACKLOG.md).

Incident 1 (12:11:47): BACKLOG.md was truncated to 0 bytes by a room worker's shell
write and NO recovery copy existed -- the newest snapshot was 2h13m old.

Incident 2 (14:21:58): a stale writer pushed the 12:25 revision back over the file.
Item region was byte-identical, so the old item-count-only health check passed, and the
two orphan claim stanzas that live ABOVE the first `### BL-` heading came back with it
(`status: claimed` outside any item block => every naive open/claimed count probe
inflates: claimed 15 vs real 13). Header-only rollbacks are now a first-class failure.

This makes both impossible:
  --check   (default, cron): HARD CHECKS first (see INVARIANTS), then
            * header corrupt (orphan state line / status-count != item count):
              repair the HEADER ONLY from BACKLOG.md.lastgood, keep live items, never
              snapshot a corrupt file (a rolled-back header must not become last-good);
            * live degenerate (0 bytes / < MIN_ITEMS `### BL-`) with a snapshot: RESTORE
              it and preserve the corpse;
            * otherwise: snapshot live + refresh BACKLOG.md.lastgood.
Never deletes anything; never writes unless there is something to record.

INVARIANTS (all must hold for a file to be snapshot-eligible):
  I1  no `^status:` line before the first `### BL-` heading (no orphan claim stanzas)
  I2  count(`^status:`) == count(`### BL-`) (exactly one state line per item)
  I3  items(LIVE) >= MIN_ITEMS
"""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys
import time

POOL = pathlib.Path("/home/host/opikernel/agentic-pool")
LIVE = POOL / "BACKLOG.md"
STORE = POOL / ".backlog-lastgood"
LASTGOOD = POOL / "BACKLOG.md.lastgood"
MIN_ITEMS = 20  # healthy queue has 24; a 0-byte file has 0
STATE_RE = re.compile(r"^status:", re.MULTILINE)
HEAD_SPLIT = "\n### BL-"


def text(p: pathlib.Path) -> str:
    try:
        return p.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def items(p: pathlib.Path) -> int:
    t = text(p)
    if t == "" and not p.exists():
        return -1
    return t.count(HEAD_SPLIT)


def header(p: pathlib.Path) -> str:
    """Everything above the first item block -- rewritten by stale writers, so guarded."""
    return text(p).split(HEAD_SPLIT, 1)[0]


def orphan_lines(p: pathlib.Path) -> list:
    """I1: state lines sitting above the first item block (invisible to lint, inflate probes)."""
    hdr = header(p)
    return [f"line {i}: {ln}" for i, ln in enumerate(hdr.splitlines(), 1)
            if STATE_RE.match(ln)]


def state_lines(p: pathlib.Path) -> int:
    return len(STATE_RE.findall(text(p)))


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def snapshots():
    if not STORE.exists():
        return []
    return sorted(STORE.glob("BACKLOG.*.md"), key=lambda p: p.stat().st_mtime)


def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {msg}"
    print(line, flush=True)
    with (POOL / "backlog-lastgood-guard.log").open("a") as fh:
        fh.write(line + "\n")


def run(script: str) -> str:
    r = subprocess.run(["/usr/bin/python3", f"/home/host/opikernel/scripts/{script}"],
                       capture_output=True, text=True)
    out = (r.stdout or "").strip().splitlines()
    return out[-1] if out else f"no output (rc={r.returncode})"


def restore_from_snapshot(n: int, tag: str = "truncated") -> int:
    """Restore LIVE wholesale from the newest snapshot, keeping the corpse."""
    snaps = snapshots()
    if not snaps:
        log(f"ALARM items={n} size={LIVE.stat().st_size if LIVE.exists() else 'MISSING'} "
            f"and NO last-good snapshot exists -- manual rebuild required")
        return 2
    best = snaps[-1]
    corpse = POOL / f"BACKLOG.md.{tag}-{time.strftime('%Y%m%d-%H%M%S')}"
    if LIVE.exists():
        shutil.copy2(LIVE, corpse)
    shutil.copy2(best, LIVE)
    log(f"ALARM items={n} -> RESTORED from {best.name} "
        f"(items={items(LIVE)} md5={md5(LIVE)}); corpse kept at {corpse.name}")
    # re-verify lint + mirror so the board cannot stay stale after a restore
    log("lint: " + run("backlog-section-lint.py"))
    log("kanban mirror re-run after restore: " + run("sync-backlog-to-kanban.py"))
    return 1


def repair_header() -> int:
    """Header-only restore: keep the live item region, take the header from last-good."""
    good = header(LASTGOOD)
    if not good or orphan_lines(LASTGOOD):
        log("ALARM corrupt header and last-good header is unusable -- manual rebuild required")
        return 2
    live_text = text(LIVE)
    if HEAD_SPLIT not in live_text:
        # ALL item headings stripped by a writer: there is no item region to split on, so a
        # header-only repair is impossible. This used to `return 2` with NO log line, so the
        # 5-min cron re-logged the I1 ALARM forever and never repaired (observed 09-21
        # 01:16-01:22: 24 `status:` lines, 0 `### BL-` headings, live == lastgood minus
        # headings). Escalate to the snapshot restore path instead of bailing silently.
        log(f"ALARM I1 with ZERO item headings (states={state_lines(LIVE)}, "
            f"orphans={len(orphan_lines(LIVE))}) -- header repair impossible, "
            f"escalating to snapshot restore")
        return restore_from_snapshot(state_lines(LIVE), tag="headings-stripped")
    corpse = POOL / f"BACKLOG.md.hdr-rolledback-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(LIVE, corpse)
    live_text = live_text.replace(header(LIVE), good, 1)
    LIVE.write_text(live_text)
    log(f"ALARM header rolled back (orphans={len(orphan_lines(corpse))}) -> header repaired "
        f"from {LASTGOOD.name}; items untouched; corpse kept at {corpse.name}")
    log(f"post-repair md5={md5(LIVE)} items={items(LIVE)} orphans={len(orphan_lines(LIVE))} "
        f"states={state_lines(LIVE)}")
    log("lint: " + run("backlog-section-lint.py"))
    log("kanban mirror re-run after header repair: " + run("sync-backlog-to-kanban.py"))
    return 1


def main() -> int:
    STORE.mkdir(exist_ok=True)
    n = items(LIVE)
    orphans = orphan_lines(LIVE)
    states = state_lines(LIVE)

    # I1/I2: header integrity is checked before anything is trusted or stored.
    if n >= 0 and orphans:
        log(f"ALARM I1 violated: {len(orphans)} orphan state line(s) above the first item "
            f"({'; '.join(orphans)})")
        return repair_header()
    if n >= 0 and states != n:
        log(f"ALARM I2 violated: {states} `status:` lines for {n} item blocks")
        return repair_header()

    if n >= MIN_ITEMS:
        m = md5(LIVE)
        dest = STORE / f"BACKLOG.{m}.md"
        if not dest.exists():
            shutil.copy2(LIVE, dest)
            shutil.copy2(LIVE, LASTGOOD)
            log(f"OK items={n} states={states} md5={m} hdr={hashlib.md5(header(LIVE).encode()).hexdigest()[:8]} "
                f"snapshot stored ({LIVE.stat().st_size} B)")
        return 0

    # degenerate live file (< MIN_ITEMS headings)
    return restore_from_snapshot(n, tag="truncated")


if __name__ == "__main__":
    sys.exit(main())
