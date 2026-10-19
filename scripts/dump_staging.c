/* dump_staging.c — after egl_clear_test runs, dump the whole staging page.
 * Build: gcc -O1 -o dump_staging dump_staging.c -ldl -lm
 * Run with the same env as egl_clear_test.
 */
#include <stdio.h>
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

#define EGL_SURFACE_TYPE 0x3033
#define EGL_PBUFFER_BIT 0x0001
#define EGL_RED_SIZE 0x3024
#define EGL_GREEN_SIZE 0x3023
#define EGL_BLUE_SIZE 0x3022
#define EGL_ALPHA_SIZE 0x3021
#define EGL_NONE 0x3038
#define EGL_RENDERABLE_TYPE 0x3040
#define EGL_OPENGL_ES2_BIT 0x0004
#define EGL_OPENGL_ES_API 0x30A0
#define EGL_CONTEXT_CLIENT_VERSION 0x3098
#define EGL_WIDTH 0x3057
#define EGL_HEIGHT 0x3056

static EGLDisplay (*p_eglGetDisplay)(void *);
static EGLBoolean (*p_eglInitialize)(EGLDisplay, EGLint *, EGLint *);
static EGLBoolean (*p_eglBindAPI)(EGLenum);
static EGLBoolean (*p_eglChooseConfig)(EGLDisplay, const EGLint *, void *, EGLint, EGLint *);
static EGLSurface (*p_eglCreatePbufferSurface)(EGLDisplay, void *, const EGLint *);
static EGLContext (*p_eglCreateContext)(EGLDisplay, void *, void *, const EGLint *);
static EGLBoolean (*p_eglMakeCurrent)(EGLDisplay, EGLSurface, EGLSurface, EGLContext);

static void (*p_glClearColor)(float, float, float, float);
static void (*p_glClear)(unsigned);
static void (*p_glFinish)(void);
#define GL_COLOR_BUFFER_BIT 0x4000

int main(void)
{
   void *egl = dlopen("libEGL.so.1", RTLD_NOW | RTLD_GLOBAL);
   EGLDisplay dpy; EGLSurface surf; EGLContext ctx; void *cfg = NULL; EGLint nc = 0, maj = 0, min = 0;
   const EGLint cfg_attribs[] = { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
      EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
      EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE };
   const EGLint pb_attribs[] = { EGL_WIDTH, 128, EGL_HEIGHT, 128, EGL_NONE };
   const EGLint ctx_attribs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };

   p_eglGetDisplay = dlsym(egl, "eglGetDisplay");
   p_eglInitialize = dlsym(egl, "eglInitialize");
   p_eglBindAPI = dlsym(egl, "eglBindAPI");
   p_eglChooseConfig = dlsym(egl, "eglChooseConfig");
   p_eglCreatePbufferSurface = dlsym(egl, "eglCreatePbufferSurface");
   p_eglCreateContext = dlsym(egl, "eglCreateContext");
   p_eglMakeCurrent = dlsym(egl, "eglMakeCurrent");

   dpy = p_eglGetDisplay((void *)0);
   p_eglInitialize(dpy, &maj, &min);
   p_eglBindAPI(EGL_OPENGL_ES_API);
   if (!p_eglChooseConfig(dpy, cfg_attribs, &cfg, 1, &nc) || nc < 1) {
      printf("DUMP chooseConfig FAILED n=%d\n", nc); return 1;
   }
   surf = p_eglCreatePbufferSurface(dpy, cfg, pb_attribs);
   ctx = p_eglCreateContext(dpy, cfg, NULL, ctx_attribs);
   p_eglMakeCurrent(dpy, surf, surf, ctx);

   void *gl = dlopen("libGLESv2.so.2", RTLD_NOW | RTLD_GLOBAL);
   p_glClearColor = dlsym(gl, "glClearColor");
   p_glClear = dlsym(gl, "glClear");
   p_glFinish = dlsym(gl, "glFinish");

   /* Clear RED (single clear, then long sleep so the FW either completes or faults). */
   p_glClearColor(1.0f, 0.0f, 0.0f, 1.0f);
   p_glClear(GL_COLOR_BUFFER_BIT);
   if (p_glFinish) p_glFinish();
   usleep(800000);

   printf("DUMP done clearing; sleeping so the process stays alive with the BO mapped\n");
   sleep(60);
   return 0;
}
