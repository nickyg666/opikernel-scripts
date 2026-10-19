// M3 probe v2 - correct cs from mapped BO address, using kernel structs
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
    int ret = -1;
    struct drm_version ver;
    struct drm_pvr_ioctl_create_vm_context_args vm_ctx;
    struct drm_pvr_ioctl_create_bo_args create_bo;
    struct drm_pvr_ioctl_vm_map_args vmmap;
    struct drm_pvr_ioctl_create_context_args ctx;
    uint8_t fw_stream[192];

    fd = open("/dev/dri/renderD128", O_RDWR);
    if (fd < 0) { perror("open renderD128"); return 1; }
    printf("OK   open renderD128\n");

    memset(&ver, 0, sizeof(ver));
    if (ioctl(fd, DRM_IOCTL_VERSION, &ver) < 0) { perror("VERSION"); return 1; }
    printf("OK   DRM_IOCTL_VERSION\n");

    // Create VM context
    memset(&vm_ctx, 0, sizeof(vm_ctx));
    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_VM_CONTEXT, &vm_ctx) < 0) {
        perror("CREATE_VM_CONTEXT"); return 1;
    }
    printf("OK   create VM ctx (handle=%u)\n", vm_ctx.handle);

    // Create callstack BO (4096 bytes, device uncached)
    memset(&create_bo, 0, sizeof(create_bo));
    create_bo.size = 4096;
    create_bo.flags = DRM_PVR_BO_BYPASS_DEVICE_CACHE | DRM_PVR_BO_ALLOW_CPU_USERSPACE_ACCESS;
    if (ioctl(fd, DRM_IOCTL_PVR_CREATE_BO, &create_bo) < 0) {
        perror("CREATE_BO"); return 1;
    }
    printf("OK   create callstack BO (handle=%u)\n", create_bo.handle);

    // VM_MAP the BO at heap base 0xe1c0000000
    memset(&vmmap, 0, sizeof(vmmap));
    vmmap.vm_context_handle = vm_ctx.handle;
    vmmap.device_addr = 0xe1c0000000ULL; /* heap base from dmesg */
    vmmap.handle = create_bo.handle;
    vmmap.offset = 0;
    vmmap.size = 4096;
    if (ioctl(fd, DRM_IOCTL_PVR_VM_MAP, &vmmap) < 0) {
        perror("VM_MAP"); return 1;
    }
    printf("OK   vm map (device_addr=0x%llx)\n", (unsigned long long)vmmap.device_addr);

    // Build static context state (192 bytes)
    memset(fw_stream, 0, sizeof(fw_stream));
    // Stream header: [u32 total_len=164][u32 padding=0]
    fw_stream[0] = 164;
    fw_stream[1] = 0; fw_stream[2] = 0; fw_stream[3] = 0;
    fw_stream[4] = 0; fw_stream[5] = 0; fw_stream[6] = 0; fw_stream[7] = 0;

    // Call CREATE_CONTEXT
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
    ret = 0;

    close(fd);
    return ret;
}
