#!/bin/bash
# board_gpu_resume.sh — run ON HOST after .151 is reachable.
# Resumes pvrgl M2 TQ-clear debugging: rebuild instrumented powervr.ko (-j2 MAX per Nick),
# swap module, rerun /tmp/egl_clear_test with stage traces.
set -uo pipefail
SSH="sshpass -p orangepi ssh -F /dev/null -o StrictHostKeyChecking=no -o ConnectTimeout=10 orangepi@192.168.0.151"
B=/home/orangepi/mesa26/_build

echo "== [1/6] recreating /tmp artifacts (wiped each boot)"
$SSH "mkdir -p /tmp/glvnd && printf '{\"file_format_version\":\"1.0.0\",\"ICD\":{\"library_path\":\"/home/orangepi/mesa26/_build/src/egl/libEGL_mesa.so.0\",\"api\":\"gles2\"}}\n' > /tmp/glvnd/pvrgl_icd.json && ln -sf $B/src/gallium/targets/dri/libgallium-26.3.0-devel.so $B/src/gallium/targets/dri/powervr_dri.so && ls -l /tmp/glvnd/pvrgl_icd.json $B/src/gallium/targets/dri/powervr_dri.so"

echo "== [2/6] pushing + compiling egl_clear_test"
cat /home/host/opikernel/scripts/egl_clear_test.c | $SSH 'cat > /tmp/egl_clear_test.c'
$SSH "cd /tmp && gcc -O1 -o /tmp/egl_clear_test /tmp/egl_clear_test.c -lEGL -lGLESv2 2>&1 | head -5 || gcc -O1 -o /tmp/egl_clear_test /tmp/egl_clear_test.c 2>&1 | head -5; ls -l /tmp/egl_clear_test"

echo "== [3/6] sanity-check instrumented pvr_job.c (!ctx patch region) then rebuild module -j2"
$SSH "grep -n -A4 'if (!ctx)' /opt/kernel-build/mainline-6.18/drivers/gpu/drm/imagination/pvr_job.c | head -12; cd /opt/kernel-build/mainline-6.18 && sudo -n make -j2 M=drivers/gpu/drm/imagination 2>&1 | tail -4"
if ! $SSH "test -f /opt/kernel-build/mainline-6.18/drivers/gpu/drm/imagination/powervr.ko"; then
  echo "MODULE BUILD FAILED - inspect pvr_job.c manually, aborting before swap"; exit 1
fi

echo "== [4/6] swapping module (backup current first)"
$SSH "KO=\$(modinfo -n powervr); sudo -n cp \"\$KO\" /home/orangepi/kernel-backup-20260823/powervr.ko.pre-dbg2; sudo -n rmmod powervr && sudo -n insmod /opt/kernel-build/mainline-6.18/drivers/gpu/drm/imagination/powervr.ko && sleep 2 && ls -l /dev/dri/renderD128 && echo SWAP-OK"

echo "== [5/6] clearing dmesg + running egl_clear_test"
$SSH "sudo -n dmesg -C; B=$B; cd /tmp && LD_LIBRARY_PATH=\$B/src/egl:\$B/src/gbm:\$B/src/gallium/targets/dri:\$B/src/mapi/es2api LIBGL_DRIVERS_PATH=\$B/src/gallium/targets/dri __EGL_VENDOR_LIBRARY_FILENAMES=/tmp/glvnd/pvrgl_icd.json EGL_PLATFORM=surfaceless timeout 90 ./egl_clear_test 2>&1 | grep -vE '^TEST all|^TEST pb|^TEST es2|^TEST rgba8|^ADDDBG|^CFGDBG' | tail -16"

echo "== [6/6] kernel stage traces"
$SSH "sudo -n dmesg | grep -E 'PVRDBG' | tail -20"
echo "== DONE =="
