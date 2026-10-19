#!/usr/bin/env python3
"""PA 2026-09-20: prove scripts/sync-backlog-to-kanban.py now stamps completed_at.

Runs the REAL module against a COPY of the live board and two scratch BACKLOG files:
  pass 1: BL-91 claimed  -> board in_progress, started_at set
  pass 2: BL-91 done     -> board done, completed_at set   <-- the fix under test
"""
import importlib.util
import os
import shutil
import sqlite3
import sys

SRC = "/home/host/opikernel/scripts/sync-backlog-to-kanban.py"
TEST_DB = "/tmp/pa-kb-test.db"
TEST_BL = "/tmp/pa-backlog-test.md"
KEY = "backlog:BL-91"

shutil.copy2("/home/host/.hermes/kanban.db", TEST_DB)

spec = importlib.util.spec_from_file_location("syncer", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["syncer"] = mod
spec.loader.exec_module(mod)
mod.DB = TEST_DB
mod.BACKLOG = TEST_BL
mod.LOCK = "/tmp/pa-kb-test.lock"
mod.OWNER = {}
# parse_backlog()'s path is a DEFAULT ARG bound at def time (`def parse_backlog(path=BACKLOG)`),
# so reassigning mod.BACKLOG alone is silently ignored and the harness reads the live queue.
mod.parse_backlog.__defaults__ = (TEST_BL,)


def write_backlog(state):
    with open(TEST_BL, "w") as fh:
        fh.write("# scratch\n\n### BL-91 scratch item for completed_at proof\n"
                 "status: %s\nclaimed-by: PA\nclaimed-at: 2026-09-20 18:00:00 UTC\n"
                 "evidence: synthetic\n\n## Open\n\n### BL-92 second item\n"
                 "status: open\n\n## Blocked\n\n" % state)


def row():
    con = sqlite3.connect("file:%s?mode=ro" % TEST_DB, uri=True)
    con.row_factory = sqlite3.Row
    try:
        return con.execute("select id,status,started_at,completed_at from tasks "
                           "where idempotency_key=?", (KEY,)).fetchone()
    finally:
        con.close()


write_backlog("claimed")
mod.main()
r1 = row()
print("PASS1 state=claimed -> id=%s status=%s started_at=%s completed_at=%s"
      % (r1["id"], r1["status"], r1["started_at"], r1["completed_at"]))

write_backlog("done")
# flock is per open-file-description: the pass-1 fd still holds LOCK, so pass 2 must use a fresh one
mod.LOCK = "/tmp/pa-kb-test-2.lock"
mod.main()
r2 = row()
print("PASS2 state=done    -> id=%s status=%s started_at=%s completed_at=%s"
      % (r2["id"], r2["status"], r2["started_at"], r2["completed_at"]))

ok = r2["status"] == "done" and r2["completed_at"] is not None and r1["started_at"] is not None
print("VERDICT:", "FIX CONFIRMED (started_at + completed_at written)" if ok else "STILL BROKEN")
print("live board untouched: %d rows in live db, test db rows=%d"
      % (sqlite3.connect("file:/home/host/.hermes/kanban.db?mode=ro", uri=True)
         .execute("select count(*) from tasks").fetchone()[0],
         sqlite3.connect(TEST_DB).execute("select count(*) from tasks").fetchone()[0]))
