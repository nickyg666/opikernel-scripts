// M3 probe v3 - query heaps first, then RENDER context with correct heap addr
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

int main(void) {
    int fd;
    struct drm_version ver;
    struct drm_pvr_ioctl_dev_query_args dq;
    struct drm_pvr_dev_query_heap_info hq;
    struct drm_pvr_heap *heaps = NULL;
    struct drm_pvr_ioctl_create_vm_context_args vm_ctx;
    struct drm_pvr_ioctl_create_bo_args create_bo;
    struct drm_pvr_ioctl_vm_map_args vmmap;
    struct drm_pvr_ioctl_create_context_args ctx;
    uint8_t fw_stream[192];
    uint64_t dev_addr = 0;
    uint32_t page_align = 12;
    int i;

    fd = open("/dev/dri/renderD128", O_RDWR);
    if (fd < 0) { perror("open renderD128"); return 1; }
    printf("OK   open renderD128\n");

    memset(&ver, 0, sizeof(ver));
    if (ioctl(fd, DRM_IOCTL_VERSION, &ver) < 0) { perror("VERSION"); return 1; }
    printf("OK   DRM_IOCTL_VERSION\n");

    /* Pass 1: get heap count */
    memset(&dq, 0, sizeof(dq));
    memset(&hq, 0, sizeof(hq));
    hq.heaps.stride = sizeof(struct drm_pvr_heap);
    hq.heaps.count = 0;
    hq.heaps.array = 0;
    dq.type = DRM_PVR_DEV_QUERY_HEAP_INFO_GET;
    dq.size = sizeof(hq);
    dq.pointer = (uint64_t)&hq;
    if (ioctl(fd, DRM_IOCTL_PVR_DEV_QUERY, &dq) < 0) {
        perror("DEV_QUERY(heap count)"); return 1;
    }
    printf("OK   heap count=%u stride=%u\n", hq.heaps.count, hq.heaps.stride);

    /* Pass 2: real data */
    heaps = calloc(hq.heaps.count, sizeof(struct drm_pvr_heap));
    hq.heaps.array = (uint64_t)heaps;
    dq.size = sizeof(hq);
    if (ioctl(fd, DRM_IOCTL_PVR_DEV_QUERY, &dq) < 0) {
        perror("DEV_QUERY(heap data)"); return 1;
    }
    for (i = 0; i < (int)hq.heaps.count; i++) {
        printf("     heap[%d] base=0x%llx size=0x%llx pg=%u\n", i,
               (unsigned long long)heaps[i].base,
               (unsigned long long)heaps[i].size,
               heaps[i].page_size_log2);
        /* pick the general heap: largest size */
        if (heaps[i].size > 0 && heaps[i].size > (dev_addr ? ~0ULL : 0) && heaps[i].size >= 0x100000000ULL) {
            /* prefer the biggest */
        }
    }
    /* choose largest heap */
    {
        uint64_t best = 0; int bi = -1;
        for (i = 0; i < (int)hq.heaps.count; i++) {
            if (heaps[i].size > best) { best = heaps[i].size; bi = i; }
        }
        if (bi < 0) { printf("FAIL no usable heap\n"); return 1; }
        page_align = heaps[bi].page_size_log2;
        dev_addr = heaps[bi].base + (1ULL << 20); /* base + 1MB, page aligned */
        printf("OK   using heap[%d] base=0x%llx -> dev_addr=0x%llx (page_align=%u)\n",
               bi, (unsigned long long)heaps[bi].base,
               (unsigned long long)dev_addr, page_align);
    }
    free(heaps);

    /* Create VM context */
    memset(&vm_ctx, 0, sizeof(vm_ctx));
    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_VM_CONTEXT, &vm_ctx) < 0) {
        perror("CREATE_VM_CONTEXT"); return 1;
    }
    printf("OK   create VM ctx (handle=%u)\n", vm_ctx.handle);

    /* Create callstack BO (4096 bytes) */
    memset(&create_bo, 0, sizeof(create_bo));
    create_bo.size = 4096;
    create_bo.flags = DRM_PVR_BO_BYPASS_DEVICE_CACHE | DRM_PVR_BO_ALLOW_CPU_USERSPACE_ACCESS;
    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_BO, &create_bo) < 0) {
        perror("CREATE_BO"); return 1;
    }
    printf("OK   create callstack BO (handle=%u)\n", create_bo.handle);

    /* VM_MAP the BO */
    memset(&vmmap, 0, sizeof(vmmap));
    vmmap.vm_context_handle = vm_ctx.handle;
    vmmap.device_addr = dev_addr;
    vmmap.handle = create_bo.handle;
    vmmap.offset = 0;
    vmmap.size = 4096;
    if (ioctl(fd, DRM_IOCTL_PVR_VM_MAP, &vmmap) < 0) {
        perror("VM_MAP"); return 1;
    }
    printf("OK   vm map (device_addr=0x%llx)\n", (unsigned long long)vmmap.device_addr);

    /* Build static context state (192 bytes) - header must be TOTAL size incl. 8B header */
    memset(fw_stream, 0, sizeof(fw_stream));
    fw_stream[0] = 192; fw_stream[1] = 0; fw_stream[2] = 0; fw_stream[3] = 0;
    fw_stream[4] = 0; fw_stream[5] = 0; fw_stream[6] = 0; fw_stream[7] = 0;

    /* CREATE_CONTEXT - RENDER */
    memset(&ctx, 0, sizeof(ctx));
    ctx.type = DRM_PVR_CTX_TYPE_RENDER;
    ctx.priority = 0;
    ctx.flags = 0;
    ctx.vm_context_handle = vm_ctx.handle;
    ctx.callstack_addr = vmmap.device_addr;
    ctx.static_context_state = (uint64_t)fw_stream;
    ctx.static_context_state_len = sizeof(fw_stream);

    printf("     type=%d prio=%d flg=%d vm=%u cs=0x%llx len=%u\n",
           ctx.type, ctx.priority, ctx.flags, ctx.vm_context_handle,
           (unsigned long long)ctx.callstack_addr, ctx.static_context_state_len);

    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_CONTEXT, &ctx) < 0) {
        printf("FAIL CREATE RENDER CONTEXT errno=%d (%s)\n", errno, strerror(errno));
        close(fd);
        return 1;
    }

    printf("*** RENDER CONTEXT HANDLE = %u ***\n", ctx.handle);
    printf("== M1 COMPLETE: independent render context created ==\n");

    close(fd);
    return 0;
}
