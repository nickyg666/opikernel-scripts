/* pp_m2v2.c — M2: NULL job + BO access via powervr DRM */
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
#define CHECK(c,m) do{if(c){printf("FAIL %s (%d)\n",m,errno);return 1;}printf("OK %s\n",m);}while(0)

int main(void){
	fd=open("/dev/dri/renderD128",O_RDWR|O_CLOEXEC);
	CHECK(fd<0,"open");

	struct drm_pvr_ioctl_create_vm_context_args vm={0};
	CHECK(ioctl(fd,DRM_IOCTL_PVR_CREATE_VM_CONTEXT,&vm),"vm_ctx");

	/* Heap query */
	struct drm_pvr_dev_query_heap_info qh={0};
	struct drm_pvr_ioctl_dev_query_args dq={
		.type=DRM_PVR_DEV_QUERY_HEAP_INFO_GET,
		.size=sizeof(qh),.pointer=(uintptr_t)&qh };
	ioctl(fd,DRM_IOCTL_PVR_DEV_QUERY,&dq);
	struct drm_pvr_heap heaps[8]={0};
	qh.heaps.array=(uintptr_t)heaps;
	qh.heaps.count=8; qh.heaps.stride=sizeof(struct drm_pvr_heap);
	ioctl(fd,DRM_IOCTL_PVR_DEV_QUERY,&dq);
	printf("heap[0] base=%llx\n",(unsigned long long)heaps[0].base);

	/* BO with CPU access flags */
	uint64_t gpu_addr=heaps[0].base;
	struct drm_pvr_ioctl_create_bo_args bo={
		.size=4096,
		.flags=DRM_PVR_BO_BYPASS_DEVICE_CACHE |
		       DRM_PVR_BO_PM_FW_PROTECT };
	CHECK(ioctl(fd,DRM_IOCTL_PVR_CREATE_BO,&bo),"create_bo");

	struct drm_pvr_ioctl_vm_map_args mp={
		.vm_context_handle=vm.handle,
		.device_addr=gpu_addr,
		.handle=bo.handle,.offset=0,.size=4096};
	CHECK(ioctl(fd,DRM_IOCTL_PVR_VM_MAP,&mp),"vm_map");

	/* mmap via GEM offset ioctl for CPU access */
	struct drm_pvr_ioctl_get_bo_mmap_offset_args mmo={.handle=bo.handle};
	CHECK(ioctl(fd,DRM_IOCTL_PVR_GET_BO_MMAP_OFFSET,&mmo),"mmap_offset");
	void *m=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,mmo.offset);
	if(m==MAP_FAILED){printf("SKIP mmap test\n");} else { memset(m,0xAB,64); printf("wrote pattern\n"); munmap(m,4096);}

	/* NULL job — proper struct this time */
	struct drm_pvr_job job = {
		.type = 4, /* NULL job type */
		.context_handle = 0,
		.flags = 0,
		.cmd_stream_len = 0,
		.cmd_stream = 0,
		.sync_ops = { .stride = 0, .count = 0, .array = 0 }
	};
	struct drm_pvr_ioctl_submit_jobs_args sub = {
		.jobs = { .stride = sizeof(job), .count = 1,
			  .array = (uintptr_t)&job }
	};
	int rc = ioctl(fd, DRM_IOCTL_PVR_SUBMIT_JOBS, &sub);
	printf("NULL job: rc=%d errno=%d\n",rc,errno);
	if(!rc) printf("*** JOB SUBMISSION PIPELINE WORKS ***\n");

	close(fd);
	return 0;
}
