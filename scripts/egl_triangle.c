/* egl_triangle.c — M4: native PowerVR triangle draw via pvrgl Gallium driver.
 * Draws a red triangle on black, reads back pixels.
 * Run: EGL_PLATFORM=surfaceless LIBGL_DRIVERS_PATH=<dri_dir> ./egl_triangle
 * PVRGL_RENDER_CLEAR=1 to use render clear path (not TQ).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <dlfcn.h>
#include <EGL/egl.h>
#include <GLES2/gl2.h>

static const char *vs_src =
    "attribute vec4 a_position;\n"
    "void main() {\n"
    "  gl_Position = a_position;\n"
    "}\n";

static const char *fs_src =
    "precision mediump float;\n"
    "void main() {\n"
    "  gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0); /* red */\n"
    "}\n";

static const float triangle_verts[] = {
     0.0f,  0.5f, 0.0f, 1.0f,  /* top-center    */
    -0.5f, -0.5f, 0.0f, 1.0f,  /* bottom-left   */
     0.5f, -0.5f, 0.0f, 1.0f,  /* bottom-right  */
};

static int compile_shader(GLenum type, const char *src) {
    GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &src, NULL);
    glCompileShader(shader);
    GLint ok;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[512];
        glGetShaderInfoLog(shader, sizeof(log), NULL, log);
        fprintf(stderr, "shader compile error (%s): %s\n",
                type == GL_VERTEX_SHADER ? "VS" : "FS", log);
        glDeleteShader(shader);
        return -1;
    }
    return shader;
}

int main(int argc, char **argv) {
    void *egl = dlopen("libEGL.so.1", RTLD_NOW);
    if (!egl) { fprintf(stderr, "dlopen EGL: %s\n", dlerror()); return 1; }

    typedef EGLDisplay (*PFN_GetDisplay)(EGLNativeDisplayType);
    typedef EGLBoolean (*PFN_Init)(EGLDisplay, EGLint*, EGLint*);
    typedef EGLBoolean (*PFN_BindAPI)(EGLenum);
    typedef EGLBoolean (*PFN_ChooseConfig)(EGLDisplay, const EGLint*, EGLConfig*, EGLint, EGLint*);
    typedef EGLContext (*PFN_CreateContext)(EGLDisplay, EGLConfig, EGLContext, const EGLint*);
    typedef EGLSurface (*PFN_CreatePbufferSurface)(EGLDisplay, EGLConfig, const EGLint*);
    typedef EGLBoolean (*PFN_MakeCurrent)(EGLDisplay, EGLSurface, EGLSurface, EGLContext);
    typedef EGLBoolean (*PFN_SwapBuffers)(EGLDisplay, EGLSurface);

    PFN_GetDisplay get_display = dlsym(egl, "eglGetDisplay");
    PFN_Init init = dlsym(egl, "eglInitialize");
    PFN_BindAPI bind_api = dlsym(egl, "eglBindAPI");
    PFN_ChooseConfig choose = dlsym(egl, "eglChooseConfig");
    PFN_CreateContext create_ctx = dlsym(egl, "eglCreateContext");
    PFN_CreatePbufferSurface create_pb = dlsym(egl, "eglCreatePbufferSurface");
    PFN_MakeCurrent make_current = dlsym(egl, "eglMakeCurrent");
    PFN_SwapBuffers swap = dlsym(egl, "eglSwapBuffers");

    if (!get_display || !init || !bind_api || !choose || !create_ctx ||
        !create_pb || !make_current || !swap) {
        fprintf(stderr, "missing EGL entry points\n"); return 1;
    }

    bind_api(EGL_OPENGL_ES_API);

    EGLDisplay dpy = get_display(EGL_DEFAULT_DISPLAY);
    EGLint maj, min;
    init(dpy, &maj, &min);
    printf("EGL %d.%d\n", maj, min);

    EGLint cfg_attrs[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
        EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_NONE
    };
    EGLConfig cfg;
    EGLint n;
    if (!choose(dpy, cfg_attrs, &cfg, 1, &n) || n == 0) {
        fprintf(stderr, "eglChooseConfig failed\n"); return 1;
    }
    printf("config: %d configs matched, using [0]\n", n);

    EGLContext ctx = create_ctx(dpy, cfg, EGL_NO_CONTEXT,
        (EGLint[]){ EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE });
    if (!ctx) { fprintf(stderr, "eglCreateContext failed\n"); return 1; }
    printf("context created\n");

    EGLint pb_attrs[] = { EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE };
    EGLSurface surf = create_pb(dpy, cfg, pb_attrs);
    if (!surf) { fprintf(stderr, "eglCreatePbufferSurface failed\n"); return 1; }
    printf("pbuffer surface 64x64\n");

    make_current(dpy, surf, surf, ctx);

    /* Load GLES2 */
    void *gl = dlopen("libGLESv2.so.2", RTLD_NOW);
    if (!gl) { fprintf(stderr, "dlopen GLESv2: %s\n", dlerror()); return 1; }
    #define GL_SYM(ret, name, ...) typedef ret(*name##_t)(__VA_ARGS__); name##_t name;
    GL_SYM(unsigned, glGetError,)
    GL_SYM(void*, glGetString, unsigned)
    GL_SYM(void, glClearColor, float, float, float, float)
    GL_SYM(void, glClear, unsigned)
    GL_SYM(void, glViewport, int, int, int, int)
    GL_SYM(unsigned, glCreateShader, unsigned)
    GL_SYM(void, glShaderSource, unsigned, int, const char**, const int*)
    GL_SYM(void, glCompileShader, unsigned)
    GL_SYM(void, glGetShaderiv, unsigned, unsigned, int*)
    GL_SYM(void, glGetShaderInfoLog, unsigned, int, int*, char*)
    GL_SYM(unsigned, glCreateProgram,)
    GL_SYM(void, glAttachShader, unsigned, unsigned)
    GL_SYM(void, glLinkProgram, unsigned)
    GL_SYM(void, glGetProgramiv, unsigned, unsigned, int*)
    GL_SYM(void, glGetProgramInfoLog, unsigned, int, int*, char*)
    GL_SYM(int, glGetAttribLocation, unsigned, const char*)
    GL_SYM(void, glEnableVertexAttribArray, unsigned)
    GL_SYM(void, glDisableVertexAttribArray, unsigned)
    GL_SYM(void, glVertexAttribPointer, unsigned, int, unsigned, unsigned char, int, const void*)
    GL_SYM(void, glUseProgram, unsigned)
    GL_SYM(void, glDrawArrays, unsigned, int, int)
    GL_SYM(void, glReadPixels, int, int, int, int, unsigned, unsigned, void*)
    #undef GL_SYM
    #define GL_SYM(ret, name, ...) name = dlsym(gl, #name); if (!name) { fprintf(stderr, "missing " #name "\n"); return 1; }
    GL_SYM(unsigned, glGetError,)
    GL_SYM(void*, glGetString, unsigned)
    GL_SYM(void, glClearColor, float, float, float, float)
    GL_SYM(void, glClear, unsigned)
    GL_SYM(void, glViewport, int, int, int, int)
    GL_SYM(unsigned, glCreateShader, unsigned)
    GL_SYM(void, glShaderSource, unsigned, int, const char**, const int*)
    GL_SYM(void, glCompileShader, unsigned)
    GL_SYM(void, glGetShaderiv, unsigned, unsigned, int*)
    GL_SYM(void, glGetShaderInfoLog, unsigned, int, int*, char*)
    GL_SYM(unsigned, glCreateProgram,)
    GL_SYM(void, glAttachShader, unsigned, unsigned)
    GL_SYM(void, glLinkProgram, unsigned)
    GL_SYM(void, glGetProgramiv, unsigned, unsigned, int*)
    GL_SYM(void, glGetProgramInfoLog, unsigned, int, int*, char*)
    GL_SYM(int, glGetAttribLocation, unsigned, const char*)
    GL_SYM(void, glEnableVertexAttribArray, unsigned)
    GL_SYM(void, glDisableVertexAttribArray, unsigned)
    GL_SYM(void, glVertexAttribPointer, unsigned, int, unsigned, unsigned char, int, const void*)
    GL_SYM(void, glUseProgram, unsigned)
    GL_SYM(void, glDrawArrays, unsigned, int, int)
    GL_SYM(void, glReadPixels, int, int, int, int, unsigned, unsigned, void*)

    printf("GL_VENDOR: %s\n", (char*)glGetString(0x1F00));
    printf("GL_RENDERER: %s\n", (char*)glGetString(0x1F01));
    printf("GL_VERSION: %s\n", (char*)glGetString(0x1F02));

    /* compile shaders */
    int vs = compile_shader(GL_VERTEX_SHADER, vs_src);
    int fs = compile_shader(GL_FRAGMENT_SHADER, fs_src);
    if (vs < 0 || fs < 0) return 1;
    unsigned prog = glCreateProgram();
    glAttachShader(prog, vs); glAttachShader(prog, fs);
    glLinkProgram(prog);
    int linked;
    glGetProgramiv(prog, GL_LINK_STATUS, &linked);
    if (!linked) {
        char log[512];
        glGetProgramInfoLog(prog, sizeof(log), NULL, log);
        fprintf(stderr, "link error: %s\n", log);
        return 1;
    }
    printf("program linked: %u\n", prog);

    int loc = glGetAttribLocation(prog, "a_position");
    printf("a_position loc: %d\n", loc);

    glViewport(0, 0, 64, 64);
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f); /* black */
    glClear(GL_COLOR_BUFFER_BIT);
    glError();

    glUseProgram(prog);
    glEnableVertexAttribArray(loc);
    glVertexAttribPointer(loc, 4, GL_FLOAT, GL_FALSE, 0, triangle_verts);
    glError();

    /* Draw triangle */
    glDrawArrays(GL_TRIANGLES, 0, 3);
    unsigned err = glGetError();
    printf("glDrawArrays err: 0x%x\n", err);

    glDisableVertexAttribArray(loc);
    glUseProgram(0);

    /* Read back center pixel — should be red */
    uint8_t px[4];
    glReadPixels(32, 32, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
    printf("pixel @32,32 = %02x %02x %02x %02x\n", px[0], px[1], px[2], px[3]);

    /* Also check corners */
    uint8_t ul[4], ur[4], lr[4], ll[4];
    glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, ul);
    glReadPixels(63, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, ur);
    glReadPixels(63, 63, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, lr);
    glReadPixels(0, 63, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, ll);
    printf("corner UL=(%02x,%02x,%02x) UR=(%02x,%02x,%02x) LR=(%02x,%02x,%02x) LL=(%02x,%02x,%02x)\n",
           ul[0],ul[1],ul[2], ur[0],ur[1],ur[2], lr[0],lr[1],lr[2], ll[0],ll[1],ll[2]);

    /* 4x4 sample grid */
    printf("4x4 pixel grid (RGBA):\n");
    for (int y = 0; y < 4; y++) {
        printf(" row%d: ", y);
        for (int x = 0; x < 4; x++) {
            uint8_t p[4];
            glReadPixels(x * 16 + 8, y * 16 + 8, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, p);
            printf("%02x%02x%02x%02x ", p[0], p[1], p[2], p[3]);
        }
        printf("\n");
    }

    /* Result */
    if (px[0] > 200 && px[1] < 50 && px[2] < 50 && px[3] >= 200) {
        printf("TEST RESULT: PASS (red pixel at center)\n");
        return 0;
    } else {
        printf("TEST RESULT: FAIL (expected red: R>200, G<50, B<50, A>=200)\n");
        return 1;
    }
}
