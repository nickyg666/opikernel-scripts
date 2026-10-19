/*
 * spi-mirror: mirror X display onto ILI9486 SPI panel (/dev/fb-lcd).
 * Uses XGetImage + direct pixel copy for max throughput.
 * Scales via nearest-neighbor (fastest possible).
 */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <unistd.h>

static void pack_pixel(uint8_t *dst, unsigned bytes, uint32_t r, uint32_t g,
                       uint32_t b, const struct fb_bitfield *rf,
                       const struct fb_bitfield *gf,
                       const struct fb_bitfield *bf)
{
    uint32_t v = 0;
    if (rf->length) v |= ((r >> (8 - rf->length)) & ((1u << rf->length) - 1)) << rf->offset;
    if (gf->length) v |= ((g >> (8 - gf->length)) & ((1u << gf->length) - 1)) << gf->offset;
    if (bf->length) v |= ((b >> (8 - bf->length)) & ((1u << bf->length) - 1)) << bf->offset;
    for (unsigned i = 0; i < bytes; i++)
        dst[i] = (uint8_t)(v >> (8 * i));
}

int main(int argc, char **argv)
{
    Display *dpy;
    const char *disp = argc > 1 ? argv[1] : ":0";

    if (!(dpy = XOpenDisplay(disp))) {
        fprintf(stderr, "spi-mirror: cannot open display %s\n", disp);
        return 1;
    }

    int shm_major, shm_minor;
    Bool shm_avail;
    XShmQueryVersion(dpy, &shm_major, &shm_minor, &shm_avail);
    fprintf(stderr, "spi-mirror: XShm available: %s\n", shm_avail ? "yes" : "no");

    Window root = DefaultRootWindow(dpy);

    int fd = open("/dev/fb-lcd", O_RDWR);
    if (fd < 0) { perror("spi-mirror: open /dev/fb-lcd"); return 1; }

    struct fb_var_screeninfo var = {0};
    if (ioctl(fd, FBIOGET_VSCREENINFO, &var) < 0) { perror("FBIOGET_VSCREENINFO"); return 1; }

    unsigned int fbpp = var.bits_per_pixel ? var.bits_per_pixel : 16;
    unsigned int fbbits = fbpp / 8;
    size_t fbsize = (size_t)var.xres * var.yres * fbbits;
    uint8_t *panel = mmap(NULL, fbsize, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (panel == MAP_FAILED) { perror("mmap fb"); return 1; }

    int scr_w = 0, scr_h = 0;
    XShmSegmentInfo shminfo = {0};
    XImage *shm_img = NULL;

    unsigned frame = 0;
    struct timeval tv_prev = {0};
    struct timeval tv_now;
    unsigned fps_count = 0;
    unsigned fps_timer = 0;

    for (;;) {
        XWindowAttributes wa;
        if (!XGetWindowAttributes(dpy, root, &wa)) {
            usleep(200000);
            continue;
        }

        if (wa.width != scr_w || wa.height != scr_h) {
            if (shm_img) {
                XShmDetach(dpy, &shminfo);
                XDestroyImage(shm_img);
                shm_img = NULL;
            }
            scr_w = wa.width;
            scr_h = wa.height;
            fprintf(stderr, "spi-mirror: %s %dx%d -> panel %dx%d (%ubpp)\n",
                    disp, scr_w, scr_h, var.xres, var.yres, fbpp);
        }

        XImage *img = NULL;

        if (shm_avail && !shm_img) {
            shm_img = XShmCreateImage(dpy, DefaultVisual(dpy, 0), DefaultDepth(dpy, 0),
                                      ZPixmap, NULL, &shminfo, scr_w, scr_h);
            if (shm_img) {
                shminfo.shmid = shmget(IPC_PRIVATE, shm_img->bytes_per_line * shm_img->height, IPC_CREAT | 0777);
                shminfo.shmaddr = shmat(shminfo.shmid, NULL, 0);
                shm_img->data = shminfo.shmaddr;
                if (!XShmAttach(dpy, &shminfo)) {
                    XDestroyImage(shm_img);
                    shm_img = NULL;
                    shm_avail = False;
                } else {
                    XSync(dpy, False);
                }
            }
        }

        if (shm_img) {
            if (XShmGetImage(dpy, root, shm_img, 0, 0, AllPlanes))
                img = shm_img;
        }
        if (!img) {
            img = XGetImage(dpy, root, 0, 0, scr_w, scr_h, AllPlanes, ZPixmap);
        }
        if (!img) {
            fprintf(stderr, "XGetImage failed\n");
            usleep(200000);
            continue;
        }

        for (int y = 0; y < (int)var.yres; y++) {
            int sy = y * scr_h / (int)var.yres;
            sy = sy >= scr_h ? scr_h - 1 : sy;
            const uint32_t *src_row = (const uint32_t *)img->data + (size_t)sy * scr_w;

            if (fbpp == 16 && scr_w == (int)var.xres) {
                /* Fast path: same resolution, RGB565, no scaling, no divisions */
                uint16_t *dst_row = (uint16_t *)(panel + (size_t)y * var.xres * 2);
                for (int x = 0; x < (int)var.xres; x++) {
                    uint32_t px = src_row[x];
                    uint32_t r = px & 0xff;
                    uint32_t g = (px >> 8) & 0xff;
                    uint32_t b = (px >> 16) & 0xff;
                    uint16_t rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
                    dst_row[x] = rgb565;
                }
            } else {
                /* General path with scaling */
                uint8_t *dst_row = panel + (size_t)y * var.xres * fbbits;
                for (int x = 0; x < (int)var.xres; x++) {
                    int sx = x * scr_w / (int)var.xres;
                    sx = sx >= scr_w ? scr_w - 1 : sx;
                    uint32_t px = src_row[sx];
                    uint32_t r = px & 0xff;
                    uint32_t g = (px >> 8) & 0xff;
                    uint32_t b = (px >> 16) & 0xff;
                    pack_pixel(dst_row + (size_t)x * fbbits, fbbits, r, g, b,
                               &var.red, &var.green, &var.blue);
                }
            }
        }

        if (img != shm_img)
            XDestroyImage(img);

        gettimeofday(&tv_now, NULL);
        fps_count++;
        fps_timer += (tv_now.tv_sec - tv_prev.tv_sec) * 1000 + (tv_now.tv_usec - tv_prev.tv_usec) / 1000;
        tv_prev = tv_now;

        if ((frame++ & 0x3f) == 0) {
            double fps = fps_timer > 0 ? fps_count * 1000.0 / fps_timer : 0;
            fprintf(stderr, "spi-mirror: frame %u pushed, avg fps=%.1f\n", frame, fps);
            fps_count = 0;
            fps_timer = 0;
        }
    }
    return 0;
}
