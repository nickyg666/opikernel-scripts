/* egl_smoke.c — force pvrgl screen creation through EGL surfaceless. */
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>

typedef void *EGLDisplay;
typedef unsigned int EGLBoolean;
typedef void *EGLNativeDisplayType;

static EGLDisplay (*_eglGetDisplay)(void *display_id);
static EGLBoolean (*_eglInitialize)(EGLDisplay dpy, int *maj, int *min);
static const char *(*_eglQueryString)(EGLDisplay dpy, int name);
static EGLBoolean (*_eglTerminate)(EGLDisplay dpy);

#define EGL_EXTENSIONS 0x3055

int main(int argc, char **argv)
{
   const char *lib = argc > 1 ? argv[1] : "libEGL.so.1";
   void *h = dlopen(lib, RTLD_NOW | RTLD_GLOBAL);
   if (!h) {
      printf("SMOKE dlopen(%s): %s\n", lib, dlerror());
      return 1;
   }

   _eglGetDisplay = dlsym(h, "eglGetDisplay");
   _eglInitialize = dlsym(h, "eglInitialize");
   _eglQueryString = dlsym(h, "eglQueryString");
   _eglTerminate = dlsym(h, "eglTerminate");
   if (!_eglGetDisplay || !_eglInitialize) {
      printf("SMOKE dlsym failed\n");
      return 1;
   }

   /* EGL_DEFAULT_DISPLAY (0) with EGL_PLATFORM=surfaceless env */
   EGLDisplay dpy = _eglGetDisplay((void *)0);
   printf("SMOKE eglGetDisplay -> %p\n", dpy);
   if (!dpy)
      return 2;

   int maj = 0, min = 0;
   EGLBoolean ok = _eglInitialize(dpy, &maj, &min);
   printf("SMOKE eglInitialize -> %d (%d.%d)\n", ok, maj, min);
   if (_eglQueryString && dpy)
      printf("SMOKE exts: %.200s\n", _eglQueryString(dpy, EGL_EXTENSIONS));
   if (ok && _eglTerminate)
      _eglTerminate(dpy);
   printf("SMOKE RESULT %s\n", ok ? "PASS" : "FAIL");
   return ok ? 0 : 3;
}
