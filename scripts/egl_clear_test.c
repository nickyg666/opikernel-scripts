/* egl_clear_test.c — M2 validation: EGL/PBuffer + glClear on pvrgl.
 *
 * Run env (see memory/M2 plan):
 *   LD_LIBRARY_PATH=$B/src/egl:$B/src/gbm:$B/src/gallium/targets/dri:$B/src/mapi/es2api
 *   LIBGL_DRIVERS_PATH=$B/src/gallium/targets/dri
 *   __EGL_VENDOR_LIBRARY_FILENAMES=/tmp/glvnd/pvrgl_icd.json
 *   EGL_PLATFORM=surfaceless ./egl_clear_test
 *
 * M3.5 step 1: PVRGL_TEST_PDS=1 runs PDS drawindirect generation test
 */

#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <stdint.h>

typedef void *EGLDisplay;
typedef void *EGLSurface;
typedef void *EGLContext;
typedef unsigned int EGLBoolean;
typedef unsigned int EGLenum;
typedef intptr_t EGLAttrib;
typedef int EGLint;

#define EGL_SURFACE_TYPE      0x3033
#define EGL_PBUFFER_BIT       0x0001
#define EGL_BLUE_SIZE         0x3022
#define EGL_GREEN_SIZE        0x3023
#define EGL_RED_SIZE          0x3024
#define EGL_ALPHA_SIZE        0x3021
#define EGL_NONE              0x3038
#define EGL_RENDERABLE_TYPE   0x3040
#define EGL_OPENGL_ES2_BIT    0x0004
#define EGL_OPENGL_ES_API     0x30A0
#define EGL_CONTEXT_CLIENT_VERSION 0x3098
#define EGL_WIDTH             0x3057
#define EGL_HEIGHT            0x3056
#define EGL_COLOR_BUFFER_TYPE 0x303F

static EGLDisplay (*p_eglGetDisplay)(void *);
static EGLBoolean (*p_eglInitialize)(EGLDisplay, EGLint *, EGLint *);
static EGLBoolean (*p_eglTerminate)(EGLDisplay);
static EGLBoolean (*p_eglBindAPI)(EGLenum);
static EGLBoolean (*p_eglChooseConfig)(EGLDisplay, const EGLint *, void *,
                                       EGLint, EGLint *);
static EGLSurface (*p_eglCreatePbufferSurface)(EGLDisplay, void *, const EGLint *);
static EGLContext (*p_eglCreateContext)(EGLDisplay, void *, void *, const EGLint *);
static EGLBoolean (*p_eglMakeCurrent)(EGLDisplay, EGLSurface, EGLSurface, EGLContext);

/* GLES */
static void (*p_glClearColor)(float, float, float, float);
static void (*p_glClear)(unsigned);
static void (*p_glReadPixels)(int, int, int, int, unsigned, unsigned, void *);
static void (*p_glFinish)(void);
static const unsigned char *(*p_glGetString)(int);

#define GL_COLOR_BUFFER_BIT 0x4000
#define GL_RGBA 0x1908
#define GL_UNSIGNED_BYTE 0x1401

/* M3.5 step 1: PDS drawindirect test */
static int run_pds_test(void)
{
   void *libpvrgl = dlopen("libgallium-26.3.0-devel.so", RTLD_NOW | RTLD_GLOBAL);
   if (!libpvrgl) {
      libpvrgl = dlopen("src/gallium/targets/dri/libgallium-26.3.0-devel.so", RTLD_NOW | RTLD_GLOBAL);
   }
   if (!libpvrgl) {
      printf("PVRGL_TEST_PDS: libgallium not found, skipping PDS test\n");
      return 0;
   }

   /* The PDS test is built into libpvrgl.a which is linked into libgallium.
    * Look for a test function symbol. */
   int (*pds_test_func)(void) = dlsym(libpvrgl, "pvrgl_pds_test_main");
   if (!pds_test_func) {
      printf("PVRGL_TEST_PDS: pvrgl_pds_test_main not exported, skipping\n");
      return 0;
   }

   printf("PVRGL_TEST_PDS: Running PDS drawindirect test...\n");
   return pds_test_func();
}

int main(void)
{
   /* Check for M3.5 PDS test gate */
   if (getenv("PVRGL_TEST_PDS")) {
      return run_pds_test();
   }

   void *egl = dlopen("libEGL.so.1", RTLD_NOW | RTLD_GLOBAL);
   void *gl;
   EGLDisplay dpy;
   EGLSurface surf;
   EGLContext ctx;
   void *cfg = NULL;
   EGLint nc = 0;
   EGLint maj = 0, min = 0;
   const EGLint cfg_attribs[] = {
      EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
      EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
      EGL_NONE
   };
   const EGLint pb_attribs[] = { EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE };
   const EGLint ctx_attribs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
   unsigned char px[4];
   static unsigned char full[64*64*4];

   if (!egl) {
      printf("TEST dlopen EGL: %s\n", dlerror());
      return 1;
   }

   p_eglGetDisplay = dlsym(egl, "eglGetDisplay");
   p_eglInitialize = dlsym(egl, "eglInitialize");
   p_eglTerminate = dlsym(egl, "eglTerminate");
   p_eglBindAPI = dlsym(egl, "eglBindAPI");
   p_eglChooseConfig = dlsym(egl, "eglChooseConfig");
   p_eglCreatePbufferSurface = dlsym(egl, "eglCreatePbufferSurface");
   p_eglCreateContext = dlsym(egl, "eglCreateContext");
   p_eglMakeCurrent = dlsym(egl, "eglMakeCurrent");

   dpy = p_eglGetDisplay((void *)0);
   if (!dpy || !p_eglInitialize(dpy, &maj, &min)) {
      printf("TEST eglInitialize FAILED\n");
      return 2;
   }
   printf("TEST EGL %d.%d\n", maj, min);

   { EGLint nc_all=0; void *cfgs[256];
     EGLBoolean r1 = p_eglChooseConfig(dpy,NULL,cfgs,256,&nc_all);
     printf("TEST all r=%d n=%d\n", r1, nc_all);
     const EGLint t1[] = { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_NONE };
     EGLint n1=0; p_eglChooseConfig(dpy,t1,cfgs,256,&n1);
     printf("TEST pb n=%d\n", n1);
     const EGLint t2[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE };
     EGLint n2=0; p_eglChooseConfig(dpy,t2,cfgs,256,&n2);
     printf("TEST es2 n=%d\n", n2);
     const EGLint t3[] = { EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE };
     EGLint n3=0; p_eglChooseConfig(dpy,t3,cfgs,256,&n3);
     printf("TEST rgba8 n=%d\n", n3); }

   p_eglBindAPI(EGL_OPENGL_ES_API);
   if (!p_eglChooseConfig(dpy, cfg_attribs, &cfg, 1, &nc) || nc < 1) {
      printf("TEST chooseConfig FAILED (n=%d)\n", nc);
      return 3;
   }

   { EGLint nc_all=0; void *cfgs[256];
     EGLBoolean r1 = p_eglChooseConfig(dpy,NULL,cfgs,256,&nc_all);
     printf("TEST all r=%d n=%d\n", r1, nc_all);
     const EGLint t1[] = { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_NONE };
     EGLint n1=0; p_eglChooseConfig(dpy,t1,cfgs,256,&n1);
     printf("TEST pb n=%d\n", n1);
     const EGLint t2[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE };
     EGLint n2=0; p_eglChooseConfig(dpy,t2,cfgs,256,&n2);
     printf("TEST es2 n=%d\n", n2);
     const EGLint t3[] = { EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE };
     EGLint n3=0; p_eglChooseConfig(dpy,t3,cfgs,256,&n3);
     printf("TEST rgba8 n=%d\n", n3); }
   surf = p_eglCreatePbufferSurface(dpy, cfg, pb_attribs);
   if (!surf) {
      printf("TEST pbuffer FAILED\n");
      return 4;
   }

   ctx = p_eglCreateContext(dpy, cfg, NULL, ctx_attribs);
   if (!ctx) {
      printf("TEST createContext FAILED\n");
      return 5;
   }

   if (!p_eglMakeCurrent(dpy, surf, surf, ctx)) {
      printf("TEST makeCurrent FAILED\n");
      return 6;
   }

   gl = dlopen("libGLESv2.so.2", RTLD_NOW | RTLD_GLOBAL);
   if (!gl) {
      printf("TEST dlopen GLESv2: %s\n", dlerror());
      return 7;
   }
   p_glClearColor = dlsym(gl, "glClearColor");
   p_glClear = dlsym(gl, "glClear");
   p_glReadPixels = dlsym(gl, "glReadPixels");
   p_glFinish = dlsym(gl, "glFinish");
   p_glGetString = dlsym(gl, "glGetString");

   if (p_glGetString)
      printf("TEST GL_RENDERER=%s\n", p_glGetString(0x1F01));

   /* Poison first: fill red via CPU is impossible here, so clear GREEN then
    * RED and verify final state is RED (proves second clear hit memory). */
   p_glClearColor(0.0f, 1.0f, 0.0f, 1.0f);
   p_glClear(GL_COLOR_BUFFER_BIT);
   p_glClearColor(1.0f, 0.0f, 0.0f, 1.0f);
   p_glClear(GL_COLOR_BUFFER_BIT);
   if (p_glFinish)
      p_glFinish();
   /* No fence wired yet: give the async TQ job time to execute. */
   usleep(300000);

   memset(full, 0xEE, sizeof(full));
   p_glReadPixels(0, 0, 64, 64, GL_RGBA, GL_UNSIGNED_BYTE, full);
   { unsigned nz=0, first=(unsigned)-1, last=0, rows[64]={0};
     for (unsigned i=0;i<64*64;i++){ unsigned v=full[i*4]|(full[i*4+1]<<8)|(full[i*4+2]<<16)|(full[i*4+3]<<24);
       if (v!=0xEEEEEEEE){ nz++; if(first==(unsigned)-1)first=i; last=i; rows[i/64]++; } }
     printf("TEST coverage nz=%u/4096 first_px=%u(%u,%u) last_px=%u(%u,%u)\n",
            nz, first, first%64, first/64, last, last%64, last/64);
     for (unsigned r=0;r<64;r++) if(rows[r]) printf("TEST row %u: %u px\n", r, rows[r]);
   }
   memset(px, 0xEE, sizeof(px));
   p_glReadPixels(32, 32, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
   printf("TEST pixel @32,32 = %02x %02x %02x %02x (expect ff 00 00 ff)\n",
          px[0], px[1], px[2], px[3]);

   if (px[0] == 0xFF && px[1] == 0x00 && px[2] == 0x00 && px[3] == 0xFF) {
      printf("TEST RESULT PASS\n");
      return 0;
   }
   printf("TEST RESULT FAIL\n");
   return 10;
}