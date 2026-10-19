#!/bin/bash
# Sourced or executed: install a crontab file WITHOUT the empty-file wipe class.
#
# Why this exists (2026-09-30): the live crontab was replaced by a 0-byte file at
# 17:34, which silently killed 10 cron jobs for 13 minutes. Every crontab install
# in this tree was of the form:
#
#     TMP=$(mktemp)
#     crontab -l 2>/dev/null | grep -v '^#' | ... > "$TMP"   # <-- any failure = EMPTY
#     crontab "$TMP"                                          # <-- installs the empty
#
# `crontab -l` failing (no crontab yet, permission, cron not running) plus the
# `2>/dev/null` makes the pipeline exit 0 with zero bytes, and `crontab FILE`
# happily installs nothing. The tell is /tmp/crontab.tr.<pid> left behind at 0
# bytes: that is crontab(1)'s own staging file, so the input really was empty.
#
# Rule: never install a crontab you have not counted, and always re-read it back
# in the SAME command. `crontab -l | grep -c` right after install is the only
# proof; the install itself prints success either way.
#
# Usage:
#   source scripts/cron-install-safe.sh && cron_install_safe "$TMP"
#   cron-install-safe.sh FILE [MIN_ACTIVE_LINES]
set -u

# Canonical backup: last known-good full crontab, comments intact.
CRON_BAK="${CRON_BAK:-/home/host/opikernel/state/crontab.bak-20260930-handover.txt}"

# cron_install_safe FILE [min_active] - install or refuse, then prove by re-read.
cron_install_safe() {
  local f="${1:-}" want="${2:-1}" got n_before backup
  if [ -z "$f" ] || [ ! -s "$f" ]; then
    echo "CRON_INSTALL_REFUSED: source file '$f' missing or EMPTY" >&2
    return 1
  fi
  n_before=$(crontab -l 2>/dev/null | grep -vc '^#' || true)
  [ -n "${n_before}" ] || n_before=0

  # Back up the CURRENT crontab, comments and all, before touching it.
  backup="$CRON_BAK.preinstall-$(date +%Y%m%d-%H%M%S).txt"
  if [ "$n_before" -gt 0 ]; then
    crontab -l > "$backup" 2>/dev/null || backup=""
  fi

  if ! crontab "$f" 2>/tmp/.cron-install.err; then
    echo "CRON_INSTALL_FAILED: crontab(1) rejected the file:" >&2
    cat /tmp/.cron-install.err >&2
    return 1
  fi
  rm -f /tmp/.cron-install.err

  # PROOF, not hope: re-read the installed table.
  got=$(crontab -l 2>/dev/null | grep -vc '^#' || true)
  [ -n "${got}" ] || got=0
  if [ "$got" -lt "$want" ]; then
    echo "CRON_INSTALL_REFUSED_POST: installed only $got active lines (want >= $want);" >&2
    if [ -n "$backup" ] && [ -s "$backup" ]; then
      echo "  rolling back from $backup" >&2
      crontab "$backup" && echo "  ROLLBACK_OK ($(crontab -l | grep -vc '^#') active)" >&2
    else
      echo "  NO BACKUP TO ROLL BACK TO - manual restore required from $CRON_BAK" >&2
    fi
    return 1
  fi
  # Belt and braces: if we just nuked a table down to nothing, put it back.
  if [ "$n_before" -gt 0 ] && [ "$got" -lt "$((n_before / 2))" ]; then
    echo "CRON_SHRANK: $n_before -> $got active lines, rolling back" >&2
    [ -n "$backup" ] && crontab "$backup" && echo "  ROLLBACK_OK" >&2
    return 1
  fi
  echo "CRON_INSTALL_OK: ${n_before}->${got} active lines${backup:+ (backup $backup)}"
  return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  cron_install_safe "${1:-}" "${2:-1}"
fi
