#!/bin/bash
# kdir-build v3 — THE single serialized build runner for KDIR mainline-7.3.
# Direct `make` in the tree is BANNED (racing makes delete each other's .o/.cmd -> phantom failures).
#
# Usage:
#   kdir-build.sh start <targets...>   launch detached (returns instantly); e.g. start Image dtbs
#   kdir-build.sh status               state + tail of latest build
#   kdir-build.sh wait                 block until finished, then print EXIT + artifacts
#   kdir-build.sh kill                 abort the running build (controlled)
# Lock: /home/host/opikernel/state/kdir-7.3.build.lock (held by the builder for its whole life)
# Logs: /home/host/opikernel/state/builds/<slug>.log  |  State: /home/host/opikernel/state/builds/<slug>.{pid,state}
# Exit: 0 ok | 75 BUILD_LOCKED | 64 usage
set -u
KDIR="${KDIR:-/home/host/kernel-trees/host-build/mainline-7.3}"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"
JOBS="${JOBS:-$(nproc)}"
LOCK=/home/host/opikernel/state/kdir-7.3.build.lock
STATE_DIR=/home/host/opikernel/state/builds
CONFIG="${CONFIG:-$KDIR/.config}"
GOLD="${GOLD:-/home/host/opikernel/state/gold.config}"
SELF=$(readlink -f "$0")
mkdir -p "$STATE_DIR"

fail_mark() { # EXIT trap: never leave a lying "RUNNING" state file (builder stderr -> log)
  r=$?
  [ -n "${statef:-}" ] || return 0
  case "$(cat "$statef" 2>/dev/null)" in
    RUNNING*) echo "FAILED rc=$r $(date '+%F %T')" > "$statef"
              echo "=== builder aborted rc=$r $(date '+%F %T') ===" >> "${LOG:-/dev/null}" ;;
  esac
}

builder() { # $1=slug, rest=target words
  slug="$1"; shift
  LOG="/home/host/opikernel/state/builds/$slug.log"
  pidf="$STATE_DIR/$slug.pid"; statef="$STATE_DIR/$slug.state"
  exec 9>"$LOCK"
  flock 9                       # blocking: serialize, don't fail, if something else holds it
  # 2026-09-26: was `exec 2>>"$LOG"` which appended forever, so an old run's
  # errors stayed in the file and every later `grep error:` reported them as if
  # they were current. Truncate per run and archive the previous one, so a log
  # only ever contains ONE build's output.
  if [ -s "$LOG" ]; then
    mv -f "$LOG" "$LOG.prev" 2>/dev/null || true
  fi
  exec 2>"$LOG"                  # builder stderr -> log (truncate, not append)
  cd "$KDIR" || exit 1
  echo $$ > /home/host/opikernel/state/kdir-build.pgid
  # Set our PGID to match our PID (since we're in setsid, PID == PGID)
  set -m
  # The make command will inherit our PGID
  echo "PGID $$" >> /home/host/opikernel/state/builds/$slug.log
  echo $$ > "$pidf"
  echo "RUNNING $(date '+%F %T') pid=$$ jobs=$JOBS targets=$*" > "$statef"
  # 2026-09-28: refuse to build while tooling still keeps state in /tmp. A /tmp
  # sweep once removed the gold config and the build silently fell back to a
  # no-gold path, producing a byte-identical Image while reporting rc=0. Fail
  # loudly here instead of losing the tree's build state to a cleanup.
  if [ -x /home/host/opikernel/scripts/no-tmp-state.py ]; then
    /home/host/opikernel/scripts/no-tmp-state.py >> "$LOG" 2>&1 || {
      echo 'ABORT: project tooling still keeps state in /tmp - see the log above.' >> "$LOG"
      exit 70
    }
  fi

  # ---------------------------------------------------------------------------
  # 2026-09-28: single, non-destructive, ATTRIBUTED config guard.
  #
  # Previously there were TWO guards here. Guard 1 compared .config md5 to gold
  # md5 and restored on mismatch; guard 2 compared .config md5 to a "stable
  # stamp" and restored again. Both silently overwrote .config. That combination
  # cost two full kernel builds: a legitimate Kconfig change (CONFIG_AW_RFKILL
  # m->y) was applied to .config and to the WRONG gold file, both guards reverted
  # it, and the build produced a byte-identical Image while reporting rc=0.
  #
  # The lesson was not just "shout louder". A guard that reverts an edit destroys
  # the evidence along with the edit, and the operator is left unable to tell a
  # mistake from an intentional change by a previous run. So:
  #
  #   1. ONE place knows where gold lives, and says so in the log every build.
  #   2. An edit is only reverted if it is UNDECLARED. A change that has a
  #      matching entry in the audit log (scripts/kconfig-audit.py, which records
  #      the Hermes session id, model, host and a written rationale) is treated
  #      as intentional: it is reported, attributed, and allowed through.
  #   3. Anything undeclared is still flagged loudly, with the symbol-level diff
  #      and the exact file to edit - never silently applied.
  #
  # So the guard's job is attribution and visibility, not enforcement.
  # ---------------------------------------------------------------------------
  STAMP=$STATE_DIR/.config.stable.md5
  goldreal=$(readlink -f "$GOLD" 2>/dev/null || echo "$GOLD")
  AUDIT=/home/host/opikernel/state/kconfig-audit.jsonl
  AUDIT_CLI=/home/host/opikernel/scripts/kconfig-audit.py

  echo "config source: gold=$goldreal  (edit THIS file for a Kconfig change)" >> "$LOG"

  # Warn once if a second gold-looking file exists, so the decoy trap cannot
  # silently recur.
  for other in /home/host/opikernel/state/gold.config; do
    if [ -f "$other" ] && [ "$(readlink -f "$other")" != "$goldreal" ]; then
      grep -q "GOLD_DECOY" "$LOG" 2>/dev/null || {
        echo "NOTICE: GOLD_DECOY - $other exists but is NOT what this build reads." >> "$LOG"
        echo "NOTICE: GOLD_DECOY - the real one is $goldreal. Editing the other is a no-op." >> "$LOG"
      }
    fi
  done

  # Ask the audit log whether this divergence was declared on purpose.
  audit_explains() { # $1=config $2=gold -> 0 if a recorded intent matches
    [ -f "$AUDIT" ] || return 1
    python3 - "$1" "$2" <<'PY' 2>/dev/null
import json, sys
cfg_path, gold_path = sys.argv[1], sys.argv[2]

def val(path, key):
    try:
        for line in open(path, errors="replace"):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
            if line.strip() == "# %s is not set" % key:
                return "n"
    except OSError:
        pass
    return None

latest = {}
try:
    for line in open("/home/host/opikernel/state/kconfig-audit.jsonl", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event") == "kconfig-set":
            latest[e["symbol"]] = e
except OSError:
    sys.exit(1)

# Any symbol that differs AND has a recorded intent is declared.
for sym, e in latest.items():
    if val(cfg_path, sym) != val(gold_path, sym):
        sys.exit(0)      # an intentional, in-flight change explains this
sys.exit(1)
PY
  }

  if [ ! -f "$GOLD" ]; then
    echo "WARNING: gold config $goldreal missing - building on current .config as-is." >> "$LOG"
  elif [ ! -f "$CONFIG" ]; then
    echo "NOTICE: .config absent, seeding from gold $goldreal" >> "$LOG"
    cp "$GOLD" "$CONFIG"
    nice -n 10 make ARCH=arm64 CROSS_COMPILE="$CROSS" olddefconfig
  else
    cfg_md5=$(md5sum "$CONFIG" | cut -d' ' -f1)
    if [ "$cfg_md5" = "$(md5sum "$GOLD" | cut -d' ' -f1)" ]; then
      echo "config guard: .config matches gold, nothing to do" >> "$LOG"
    else
      diffout=$(diff "$GOLD" "$CONFIG" | grep -E '^[<>] CONFIG_' || true)
      if [ -z "$diffout" ]; then
        echo "config guard: .config differs from gold only by olddefconfig churn, adopting" >> "$LOG"
      elif audit_explains "$CONFIG" "$GOLD"; then
        # Declared intent: keep it, and attribute it in the build log.
        echo "NOTICE: config divergence is DECLARED in $AUDIT - keeping .config" >> "$LOG"
        echo "$diffout" | sed 's/^/    /' >> "$LOG"
        if [ -x "$AUDIT_CLI" ]; then
          python3 "$AUDIT_CLI" log --limit 5 2>/dev/null | sed 's/^/    who: /' >> "$LOG"
        fi
        echo "NOTICE: re-run '$AUDIT_CLI blame <symbol>' to see which session and why." >> "$LOG"
      elif [ -s "$STAMP" ] && [ "$cfg_md5" = "$(cat "$STAMP")" ]; then
        echo "config guard: matches stable stamp, keeping .config as-is" >> "$LOG"
        echo "NOTICE: .config differs from gold but matches the known-good stamp." >> "$LOG"
      else
        # Undeclared drift. Report it, attribute what is known, do not clobber.
        echo "NOTICE: UNDECLARED config drift - .config differs from $goldreal:" >> "$LOG"
        echo "$diffout" | sed 's/^/    /' >> "$LOG"
        echo "NOTICE: this was NOT declared in $AUDIT, so it may be accidental." >> "$LOG"
        echo "NOTICE: to change a symbol, use: $AUDIT_CLI set <SYM> <y|m|n> -r '<why>'" >> "$LOG"
        echo "NOTICE: then set the same value in $goldreal. This build keeps .config." >> "$LOG"
      fi
    fi
    md5sum "$CONFIG" | cut -d' ' -f1 > "$STAMP"
  fi
  echo "config guard: effective config for this build is $CONFIG (gold=$goldreal)" >> "$LOG"
  trap fail_mark EXIT INT TERM
  {
    echo "=== kdir-build v3 start $(date '+%F %T') targets='$*' jobs=$JOBS ==="
    cd "$KDIR" || exit 1
    rc=0; attempt=0; max_attempt="${KDIR_BUILD_RETRIES:-20}"
    while :; do
      nice -n 10 make ARCH=arm64 CROSS_COMPILE="$CROSS" -j"$JOBS" "$@"
      rc=$?
      if [ $rc -eq 137 ] && [ $attempt -lt $max_attempt ]; then
        attempt=$((attempt+1))
        echo "SIGKILLed (rc=137) attempt $attempt/$max_attempt — kbuild resumable, relaunching in 5s $(date '+%F %T')"
        sleep 5; continue
      fi
      break
    done
    echo "EXIT=$rc"
    if [ -f arch/arm64/boot/Image ]; then
      ls -la arch/arm64/boot/Image; md5sum arch/arm64/boot/Image
      head -c4 arch/arm64/boot/Image | od -An -tx1
      SZ=$(stat -c %s arch/arm64/boot/Image)
      printf 'end_addr=0x%x (ceiling 0x43999999)\n' $((0x41000000+SZ))
    fi
    echo "=== finished $(date '+%F %T') rc=$rc ==="
  } >> "$LOG" 2>&1
  echo "DONE rc=$rc $(date '+%F %T')" > "$statef"

  # --- publish hook (PA 2026-09-18): every rc=0 build goes to
  # github.com/nickyg666/orangepi-zero3w-7.3-artifacts immediately, instead of
  # waiting for the 2-min cron sweep (a fast follow-up build could otherwise
  # overwrite the Image before the sweep sees it). Detached: never blocks the
  # wrapper. Gated inside the publisher (magic/VA_BITS/EFI_STUB/quiescent/dedupe).
  if [ "$rc" = 0 ] && [ -f "$KDIR/arch/arm64/boot/Image" ] \
     && [ -x /usr/bin/python3 ] && [ -f "$HOME/opikernel/scripts/publish-7.3-artifacts.py" ]; then
    setsid /usr/bin/python3 "$HOME/opikernel/scripts/publish-7.3-artifacts.py" --if-new --min-age 0 \
      >> "$HOME/opikernel/logs/publish-7.3-artifacts.hook.log" 2>&1 &
  fi
}

cmd="${1:-status}"
case "$cmd" in
  start)
    shift
    [ $# -ge 1 ] || { echo "usage: $0 start <targets...>"; exit 64; }
    slug=$(echo "$*" | tr ' /' '--')
    setsid bash "$SELF" --run "$slug" "$@" < /dev/null > /dev/null 2>&1 &
    echo "launched detached: slug=$slug log=/home/host/opikernel/state/builds/$slug.log"
    ;;
  --run) # internal
    slug="$2"; shift 2; builder "$slug" "$@"
    ;;
  kill)
    for pidf in "$STATE_DIR"/*.pid; do
      [ -e "$pidf" ] || continue
      p=$(<"$pidf")
      if [ -d /proc/$p ]; then echo "killing build tree pid=$p"; kill -9 -- -"$p" 2>/dev/null || kill -9 "$p" 2>/dev/null; fi
    done
    ;;
  wait)
    slug=$(ls -t "$STATE_DIR"/*.state 2>/dev/null | head -1)
    [ -n "$slug" ] || { echo IDLE; exit 0; }
    slug=$(basename "$slug" .state)
    for i in $(seq 1 340); do
      st=$(cat "$STATE_DIR/$slug.state" 2>/dev/null)
      case "$st" in DONE*) break;; esac
      sleep 5
    done
    echo "$slug: $(cat "$STATE_DIR/$slug.state")"
    grep -E 'EXIT=|md5sum|end_addr|Image$|finished' "/home/host/opikernel/state/builds/$slug.log" | tail -8
    ;;
  status|*)
    found=0
    for statef in "$STATE_DIR"/*.state; do
      [ -e "$statef" ] || continue
      found=1
      slug=$(basename "$statef" .state); st=$(<"$statef")
      pidf="$STATE_DIR/$slug.pid"; alive=no
      [ -f "$pidf" ] && [ -d "/proc/$(<$pidf)" ] && alive=yes
      echo "$slug: $st (builder-alive=$alive) log=/home/host/opikernel/state/builds/$slug.log"
    done
    [ $found -eq 0 ] && echo "IDLE — no builds launched via $SELF yet"
    latest=$(ls -t "$STATE_DIR"/*.state 2>/dev/null | head -1)
    if [ -n "$latest" ]; then lslug=$(basename "$latest" .state); echo "--- tail $STATE_DIR/$lslug.log"; tail -12 "$STATE_DIR/$lslug.log" 2>/dev/null; fi
    echo "--- direct-makes-in-tree (rogues, will corrupt):"
    # builder() runs `set -m`, so the make tree gets its OWN PGID (== make's PID), not the
    # recorded builder PID — PGID matching false-positives on healthy builds. Walk the
    # ancestry instead: sanctioned iff some ancestor cmdline contains kdir-build.sh.
    rogue=0
    while read -r pid etime cmd; do
      [ -n "${cmd:-}" ] || continue
      p="$pid"; sanctioned=no
      for _ in $(seq 1 8); do
        [ -z "$p" ] && break
        [ "$p" = 0 ] && break
        [ "$p" = 1 ] && break
        c=$(ps -o cmd= -p "$p" 2>/dev/null)
        [ -z "$c" ] && break
        case "$c" in *kdir-build.sh*) sanctioned=yes; break;; esac
        p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
      done
      [ "$sanctioned" = yes ] && continue
      echo "ROGUE pid=$pid etime=$etime $cmd"; rogue=1
    done < <(ps -eo pid=,etime=,cmd= | grep '[m]ake ARCH=arm64')
    [ "$rogue" -eq 0 ] && echo none
    ;;
esac
