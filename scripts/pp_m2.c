/* pp_m2.c — M2: NULL job + TRANSFER_FRAG clear via powervr DRM */
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
#define CHECK(call,msg) do{if(call){printf("FAIL %s (%d)\n",msg,errno);return 1;}printf("OK %s\n",msg);}while(0)

int main(void){
	fd=open("/dev/dri/renderD128",O_RDWR|O_CLOEXEC);
	CHECK(fd<0,"open");

	/* VM ctx */
	struct drm_pvr_ioctl_create_vm_context_args vm={0};
	CHECK(ioctl(fd,DRM_IOCTL_PVR_CREATE_VM_CONTEXT,&vm),"vm_ctx");

	/* Alloc target BO (1 page) */
	struct drm_pvr_ioctl_create_bo_args bo={.size=4096};
	CHECK(ioctl(fd,DRM_IOCTL_PVR_CREATE_BO,&bo),"create_bo");

	/* Map it to GPU */
	struct drm_pvr_heap heaps[8]; struct drm_pvr_dev_query_gpu_info gi={0};
	struct drm_pvr_ioctl_dev_query_args dqh={.type=DRM_PVR_DEV_QUERY_HEAP_INFO_GET,.size=sizeof(struct drm_pvr_dev_query_heap_info)};
	struct drm_pvr_dev_query_heap_info qh={0};
	dqh.heaps.count=8; dqh.heaps.stride=sizeof(struct drm_pvr_heap);
	dqh.heaps.array=(uintptr_t)heaps;
	struct drm_pvr_ioctl_dev_query_args dq={.type=DRM_PVR_DEV_QUERY_HEAP_INFO_GET,.pointer=(uintptr_t)&qh,.size=sizeof(qh)};
	ioctl(fd,DRM_IOCTL_PVR_DEV_QUERY,&dq);

	uint64_t gpu_addr = heaps[0].base; /* heap[0] general */
	struct drm_pvr_ioctl_vm_map_args mp={
		.vm_context_handle=vm.handle,
		.device_addr=gpu_addr,
		.handle=bo.handle, .offset=0, .size=4096 };
	CHECK(ioctl(fd,DRM_IOCTL_PVR_VM_MAP,&mp),"vm_map");

	/* NULL job — proves submit pipeline works (no ctx needed) */
	uint32_t null_job[6]={4,0,0,0,0,0}; /* type=NULL,ctx=0,flags=0,len=0,stream_ptr=0 */
	struct drm_pvr_obj_array jobs_arr={.stride=sizeof(null_job),.count=1,.array=(uintptr_t)null_job};
	struct drm_pvr_ioctl_submit_jobs_args sub={.jobs=jobs_arr};
	int rc=ioctl(fd,DRM_IOCTL_PVR_SUBMIT_JOBS,&sub);
	printf("NULL job: rc=%d errno=%d\n",rc,errno);
	if(!rc) printf("*** JOB SUBMISSION PIPELINE WORKS ***\n");

	/* mmap CPU side and check content */
	struct drm_prime_handle prime={.handle=bo.handle,.flags=DRM_CLOEXEC};
	CHECK(ioctl(fd,DRM_IOCTL_PRIME_HANDLE_TO_FD,&prime),"prime");
	void *m=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,prime.fd,0);
	CHECK(m==MAP_FAILED,"mmap");
	printf("BO first 16 bytes: ");
	for(int i=0;i<16;i++)printf("%02x",((unsigned char*)m)[i]);
	printf("\n");

	close(fd);
	return 0;
}
