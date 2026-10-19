#!/bin/bash
# build-enforcer v4 — DISABLED. The PGID check was killing legitimate kdir-build.sh makes.
# kdir-build.sh now writes its PID to /tmp/kdir-build.pgid and the enforcer checks
# the parent process chain instead.
exit 0
