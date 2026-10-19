#!/bin/bash
# BE-20260930: audit every crontab INSTALL in the tree. An install is a `crontab
# FILE` (not `crontab -l`, not a comment, not a string). Any install in a script
# that does NOT call cron_install_safe is the 2026-09-30 17:34 wipe class.
cd /home/host/opikernel || exit 1
rc=0
printf '%-8s %-48s %s\n' STATE FILE "LINE"
for f in scripts/*.sh pvrgl-work/*.sh; do
  [ -f "$f" ] || continue
  # Lines that INSTALL a crontab. An install is `crontab FILE`.
  # Filter out only lines whose crontab invocation is a LIST (`crontab -l ...`),
  # by deleting that fragment first - a naive `grep -v 'crontab -l'` also drops
  # lines that merely mention `crontab -l` inside a trailing echo, which is how
  # the rollback install in cron-install-safe.sh was hidden from this audit.
  hits=$(grep -nE '^[[:space:]]*crontab[[:space:]]+[^[:space:]-]' "$f" 2>/dev/null \
         | sed -E 's/crontab[[:space:]]+-l[^&|;]*/ /g' \
         | grep -E '^[[:space:]]*[0-9]+:[[:space:]]*crontab[[:space:]]+[^[:space:]-]' || true)
  [ -n "$hits" ] || continue
  if grep -q 'cron_install_safe' "$f"; then
    st=GUARDED
  else
    st=UNGUARDED
    rc=1
  fi
  printf '%-8s %-48s %s\n' "$st" "$f" "$(echo "$hits" | cut -d: -f1 | tr '\n' ',')"
done
echo
[ $rc -eq 0 ] && echo "CRON_AUDIT: all crontab installs are guarded" \
              || echo "CRON_AUDIT: UNGUARDED installs present (the empty-table wipe class)"
exit $rc
