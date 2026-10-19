/* pvr_abi_probe.c FINAL — M1: independent userspace render context on powervr DRM */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <drm.h>
#include <drm_mode.h>
#include <pvr_drm.h>

static int fd;
#define CHECK(call, what) do { \
	if (call) { printf("FAIL %-28s errno=%d (%s)\n", what, errno, strerror(errno)); return 1; } \
	printf("OK   %s\n", what); } while (0)

int main(void)
{
	fd = open("/dev/dri/renderD128", O_RDWR | O_CLOEXEC);
	CHECK(fd < 0, "open renderD128");

	drm_version_t ver = {0};
	char nm[64]={0}, dt[64]={0}, ds[64]={0};
	ver.name=nm; ver.name_len=63; ver.date=dt; ver.date_len=63; ver.desc=ds; ver.desc_len=63;
	CHECK(ioctl(fd, DRM_IOCTL_VERSION, &ver), "DRM_IOCTL_VERSION");

	struct drm_pvr_ioctl_dev_query_args dq = {.type = DRM_PVR_DEV_QUERY_HEAP_INFO_GET};
	struct drm_pvr_dev_query_heap_info qh = {0};
	dq.size = sizeof(qh); dq.pointer = (uintptr_t)&qh;
	ioctl(fd, DRM_IOCTL_PVR_DEV_QUERY, &dq);
	struct drm_pvr_heap *heaps = calloc(qh.heaps.count, sizeof(*heaps));
	qh.heaps.array = (uintptr_t)heaps;
	dq.size = sizeof(qh);
	CHECK(ioctl(fd, DRM_IOCTL_PVR_DEV_QUERY, &dq), "heap query");

	/* GPU_INFO query — wakes GPU via pm_runtime before context creation */
	struct drm_pvr_ioctl_dev_query_args giq = {.type = DRM_PVR_DEV_QUERY_GPU_INFO_GET};
	uint8_t gpu_info[256] = {0};
	giq.size = sizeof(gpu_info);
	giq.pointer = (uintptr_t)gpu_info;
	CHECK(ioctl(fd, DRM_IOCTL_PVR_DEV_QUERY, &giq), "GPU_INFO query (wake)");

	/* VM context */
	struct drm_pvr_ioctl_create_vm_context_args vm = {0};
	CHECK(ioctl(fd, DRM_IOCTL_PVR_CREATE_VM_CONTEXT, &vm), "create VM ctx");

	/* Callstack BO mapped at heap[0].base + 0 (same as mesa-vulkan) */
	uint64_t cs_addr = heaps[0].base;
	struct drm_pvr_ioctl_create_bo_args cbo = {.size = 65536};
	CHECK(ioctl(fd, DRM_IOCTL_PVR_CREATE_BO, &cbo), "create callstack BO");
	struct drm_pvr_ioctl_vm_map_args mp = {
		.vm_context_handle = vm.handle,
		.device_addr = cs_addr,
		.handle = cbo.handle, .offset = 0, .size = 65536 };
	CHECK(ioctl(fd, DRM_IOCTL_PVR_VM_MAP, &mp), "vm map");

	/* RENDER context — golden params from mesa-vulkan capture:
	 * type=0(RENDER), prio=0(NORMAL), flags=0, vm_ctx=handle, cs=heap_base, len=192
	 * Stream: [u32 main_len=184][u32 pad=0][23×u64 values]
	 * Values from mesa pvr_drm_render_ctx_static_state_init — zeros OK (no content validation)
	 */
	uint32_t fwh[2] = {184, 0};
	uint64_t fwd[23] = {0};
	uint8_t fw[256];
	memset(fw, 0, sizeof(fw));
	memcpy(fw, fwh, 8);
	memcpy(fw + 8, fwd, 184);

	struct drm_pvr_ioctl_create_context_args ctx = {0};
	ctx.type = DRM_PVR_CTX_TYPE_RENDER;
	ctx.priority = 0;   /* DRM_PVR_CTX_PRIORITY_NORMAL */
	ctx.flags = 0;
	ctx.vm_context_handle = vm.handle;
	ctx.callstack_addr = cs_addr;
	ctx.static_context_state = (unsigned long long)(uintptr_t)fw;
	ctx.static_context_state_len = 192;

	printf("     type=%d prio=%d flg=%d vm=%u cs=%llx len=%u\n",
		ctx.type, ctx.priority, ctx.flags, ctx.vm_context_handle,
		(unsigned long long)ctx.callstack_addr, ctx.static_context_state_len);
	CHECK(ioctl(fd, DRM_IOCTL_PVR_CREATE_CONTEXT, &ctx), "CREATE RENDER CONTEXT");
	printf("*** RENDER CONTEXT HANDLE = %u ***\n", ctx.handle);

	struct drm_pvr_ioctl_destroy_context_args dctx = {.handle = ctx.handle};
	CHECK(ioctl(fd, DRM_IOCTL_PVR_DESTROY_CONTEXT, &dctx), "destroy ctx");
	close(fd);
	printf("\n== M1 COMPLETE: independent render context created ==\n");
	return 0;
}
