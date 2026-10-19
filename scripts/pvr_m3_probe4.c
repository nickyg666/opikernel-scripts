// M3 probe 4 - render + compute context creation, header=TOTAL semantics
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <drm/drm.h>
#include <drm/pvr_drm.h>

static int fd;

static int make_ctx(int type, uint64_t callstack_addr, void *stream, uint32_t stream_len,
                    uint32_t vm_handle, uint32_t *out_handle) {
    struct drm_pvr_ioctl_create_context_args ctx;
    memset(&ctx, 0, sizeof(ctx));
    ctx.type = type;
    ctx.priority = 0;
    ctx.flags = 0;
    ctx.vm_context_handle = vm_handle;
    ctx.callstack_addr = callstack_addr;
    ctx.static_context_state = (uint64_t)stream;
    ctx.static_context_state_len = stream_len;
    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_CONTEXT, &ctx) < 0) {
        printf("FAIL CREATE ctx type=%d errno=%d (%s)\n", type, errno, strerror(errno));
        return -1;
    }
    printf("OK   ctx type=%d handle=%u\n", type, ctx.handle);
    if (out_handle) *out_handle = ctx.handle;
    return 0;
}

int main(void) {
    struct drm_version ver;
    struct drm_pvr_ioctl_dev_query_args dq;
    struct drm_pvr_dev_query_heap_info hq;
    struct drm_pvr_heap *heaps = NULL;
    struct drm_pvr_ioctl_create_vm_context_args vm_ctx;
    struct drm_pvr_ioctl_create_bo_args create_bo;
    struct drm_pvr_ioctl_vm_map_args vmmap;
    uint8_t fw_render[192];
    uint8_t fw_compute[64];
    uint64_t dev_addr = 0;
    int i, bi = -1;
    uint64_t best = 0;
    uint32_t vmh, rendh = 0, comph = 0;

    fd = open("/dev/dri/renderD128", O_RDWR);
    if (fd < 0) { perror("open renderD128"); return 1; }
    memset(&ver, 0, sizeof(ver));
    if (ioctl(fd, DRM_IOCTL_VERSION, &ver) < 0) { perror("VERSION"); return 1; }
    printf("OK   open + version\n");

    memset(&dq, 0, sizeof(dq));
    memset(&hq, 0, sizeof(hq));
    hq.heaps.stride = sizeof(struct drm_pvr_heap);
    dq.type = DRM_PVR_DEV_QUERY_HEAP_INFO_GET;
    dq.size = sizeof(hq);
    dq.pointer = (uint64_t)&hq;
    if (ioctl(fd, DRM_IOCTL_PVR_DEV_QUERY, &dq) < 0) { perror("DEV_QUERY1"); return 1; }
    heaps = calloc(hq.heaps.count, sizeof(struct drm_pvr_heap));
    hq.heaps.array = (uint64_t)heaps;
    if (ioctl(fd, DRM_IOCTL_PVR_DEV_QUERY, &dq) < 0) { perror("DEV_QUERY2"); return 1; }
    for (i = 0; i < (int)hq.heaps.count; i++)
        if (heaps[i].size > best) { best = heaps[i].size; bi = i; }
    if (bi < 0) { printf("FAIL no heap\n"); return 1; }
    dev_addr = heaps[bi].base + (1ULL << 20);
    printf("OK   heap[%d] dev_addr=0x%llx\n", bi, (unsigned long long)dev_addr);

    memset(&vm_ctx, 0, sizeof(vm_ctx));
    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_VM_CONTEXT, &vm_ctx) < 0) { perror("VMCTX"); return 1; }
    vmh = vm_ctx.handle;

    memset(&create_bo, 0, sizeof(create_bo));
    create_bo.size = 4096;
    create_bo.flags = DRM_PVR_BO_BYPASS_DEVICE_CACHE | DRM_PVR_BO_ALLOW_CPU_USERSPACE_ACCESS;
    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_BO, &create_bo) < 0) { perror("CREATE_BO"); return 1; }

    memset(&vmmap, 0, sizeof(vmmap));
    vmmap.vm_context_handle = vmh;
    vmmap.device_addr = dev_addr;
    vmmap.handle = create_bo.handle;
    vmmap.size = 4096;
    if (ioctl(fd, DRM_IOCTL_PVR_VM_MAP, &vmmap) < 0) { perror("VM_MAP"); return 1; }
    printf("OK   vm ctx=%u bo=%u map@0x%llx\n", vmh, create_bo.handle,
           (unsigned long long)vmmap.device_addr);

    /* RENDER: 23 defs x u64 = 184B payload + 8B header = 192B, header = 192 (TOTAL) */
    memset(fw_render, 0, sizeof(fw_render));
    fw_render[0] = 192; /* total len incl header */
    if (make_ctx(DRM_PVR_CTX_TYPE_RENDER, vmmap.device_addr, fw_render, 192, vmh, &rendh) < 0)
        goto out;

    /* COMPUTE: 7 defs x u64 = 56B payload + 8B header = 64B, header = 64, callstack 0 */
    memset(fw_compute, 0, sizeof(fw_compute));
    fw_compute[0] = 64;
    if (make_ctx(DRM_PVR_CTX_TYPE_COMPUTE, 0, fw_compute, 64, vmh, &comph) < 0)
        goto out;

    printf("== RENDER + COMPUTE contexts created standalone ==\n");
out:
    close(fd);
    return 0;
}
