#!/bin/bash
# one-shot: compare the freshly rebuilt full module bundle against the previous one
cd /home/host/opikernel/stage/7.3-stage/deploy-va39 || exit 1
OLD=$(ls -1t modules-va39.tar.gz.bak-* 2>/dev/null | head -1)
NEW=modules-va39.tar.gz
echo "OLD=$OLD  NEW=$NEW"
tar tzf "$OLD" | sort > /tmp/oldlist.txt
tar tzf "$NEW" | sort > /tmp/newlist.txt
echo "--- only in OLD (missing from rebuilt) ---"
comm -23 /tmp/oldlist.txt /tmp/newlist.txt | head -40
echo "--- only in NEW ---"
comm -13 /tmp/oldlist.txt /tmp/newlist.txt | head -40
echo "old_ko=$(grep -c '\.ko$' /tmp/oldlist.txt) new_ko=$(grep -c '\.ko$' /tmp/newlist.txt)"
echo "--- key modules present? ---"
for m in powervr.ko aic8800_fdrv.ko aic_load_fw.ko gpu-sched.ko drm.ko cfg80211.ko mac80211.ko aic8800_btlpm.ko; do
  printf '%-18s old=%s new=%s\n' "$m" "$(grep -c "/$m$" /tmp/oldlist.txt)" "$(grep -c "/$m$" /tmp/newlist.txt)"
done
echo "--- vermagic of bundle powervr.ko + aic ---"
rm -rf /tmp/bunchk && mkdir -p /tmp/bunchk && tar xzf "$NEW" -C /tmp/bunchk ./lib/modules/*/kernel/drivers/gpu/drm/imagination/powervr.ko 2>/dev/null
modinfo "$(find /tmp/bunchk -name powervr.ko | head -1)" 2>/dev/null | grep vermagic
