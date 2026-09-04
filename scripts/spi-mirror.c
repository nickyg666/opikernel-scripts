/*
 * spi-mirror: mirror the primary X display (HDMI/USB-C) onto the ILI9486
 * SPI panel (/dev/fb-lcd).
 *
 * Grabs the X root window, box-filters it down to the panel resolution,
 * and writes into the ili9486 fbdev using the fb's actual pixel format
 * (read from FBIOGET_VSCREENINFO at runtime: RGB565 16bpp or XRGB8888
 * 32bpp). The kernel shadow-diff driver only pushes changed 16x16 blocks
 * over SPI, so static content costs ~0 and motion costs one frame.
 *
 * Detects X root geometry changes on the fly (resolution/scaling changes
 * are picked up the next frame, no restart needed).
 *
 * Usage: spi-mirror [display]   (default :0)
 */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <sys/time.h>
#include <sys/resource.h>

/* pack XRGB888->panel format using runtime fb bitfield */
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

/* fast path: 1:1 pixel copy with XRGB888->RGB565 conversion */
static void copy_1to1_rgb565(uint16_t *dst, const uint32_t *src,
			     int w, int h, unsigned stride16)
{
	for (int y = 0; y < h; y++) {
		const uint32_t *srow = src + (size_t)y * w;
		uint16_t *drow = dst + (size_t)y * stride16;
		for (int x = 0; x < w; x++) {
			uint32_t px = srow[x];
			uint32_t r = (px >> 16) & 0xff;
			uint32_t g = (px >> 8) & 0xff;
			uint32_t b = px & 0xff;
			/* XRGB888->RGB565: R>>3, G>>2, B>>3 */
			drow[x] = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
		}
	}
}

/* fallback: runtime bitfield box-filter (handles arbitrary bpp) */
static void box_filter_generic(uint8_t *panel, const uint32_t *fb,
			       int scr_w, int scr_h,
			       const struct fb_var_screeninfo *var)
{
	unsigned int fbbits = var->bits_per_pixel / 8;
	for (int y = 0; y < (int)var->yres; y++) {
		int y0 = y * scr_h / (int)var->yres;
		int y1 = (y + 1) * scr_h / (int)var->yres;
		if (y1 <= y0) y1 = y0 + 1;
		uint8_t *row = panel + (size_t)y * var->xres * fbbits;
		for (int x = 0; x < (int)var->xres; x++) {
			int x0 = x * scr_w / (int)var->xres;
			int x1 = (x + 1) * scr_w / (int)var->xres;
			if (x1 <= x0) x1 = x0 + 1;
			uint32_t r = 0, g = 0, b = 0;
			unsigned n = 0;
			for (int sy = y0; sy < y1; sy++) {
				const uint32_t *rowf = fb + (size_t)sy * scr_w;
				for (int sx = x0; sx < x1; sx++) {
					uint32_t px = rowf[sx];
					b += px & 0xff;
					g += (px >> 8) & 0xff;
					r += (px >> 16) & 0xff;
					n++;
				}
			}
			if (!n) n = 1;
			r = (r + n / 2) / n; g = (g + n / 2) / n; b = (b + n / 2) / n;
			pack_pixel(row + (size_t)x * fbbits, fbbits, r, g, b,
				   &var->red, &var->green, &var->blue);
		}
	}
}

int main(int argc, char **argv)
{
	const char *disp = argc > 1 ? argv[1] : ":0";

	Display *dpy = XOpenDisplay(disp);
	if (!dpy) { fprintf(stderr, "cannot open %s\n", disp); return 1; }

	/* boost priority */
	setpriority(PRIO_PROCESS, 0, -10);

	Window root = DefaultRootWindow(dpy);

	int fd = open("/dev/fb-lcd", O_RDWR);
	if (fd < 0) { perror("open /dev/fb-lcd"); return 1; }

	struct fb_var_screeninfo var = {0};
	struct fb_fix_screeninfo fix = {0};
	if (ioctl(fd, FBIOGET_VSCREENINFO, &var) < 0) { perror("FBIOGET_VSCREENINFO"); return 1; }
	ioctl(fd, FBIOGET_FSCREENINFO, &fix);

	unsigned int fbpp = var.bits_per_pixel ? var.bits_per_pixel : 16;
	unsigned int fbbits = fbpp / 8;
	size_t fbsize = (size_t)var.xres * var.yres * fbbits;
	uint8_t *panel = mmap(NULL, fbsize, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (panel == MAP_FAILED) { perror("mmap"); return 1; }

	fprintf(stderr, "spi-mirror: display=%s panel=%dx%d %ubpp stride=%u\n",
		disp, var.xres, var.yres, fbpp, fix.line_length);

	int scr_w = 0, scr_h = 0;
	uint32_t *fb = NULL;

	/* detect 1:1 RGB565 fast path */
	int fast_path = (fbpp == 16 && var.red.offset == 11 && var.red.length == 5
			 && var.green.offset == 5 && var.green.length == 6
			 && var.blue.offset == 0 && var.blue.length == 5);

	unsigned frame = 0;
	long t_frame_avg = 0;
	struct timeval t_last = {0}, t_now;

	gettimeofday(&t_last, 0);

	for (;;) {
		XWindowAttributes wa;
		if (!XGetWindowAttributes(dpy, root, &wa)) {
			usleep(200000);
			continue;
		}
		if (wa.width != scr_w || wa.height != scr_h) {
			uint32_t *nf = realloc(fb, (size_t)wa.width * wa.height * 4);
			if (!nf) { usleep(200000); continue; }
			fb = nf;
			scr_w = wa.width;
			scr_h = wa.height;
			fprintf(stderr, "spi-mirror: %s %dx%d -> %dx%d (%ubpp) fast=%d\n",
				disp, scr_w, scr_h, var.xres, var.yres, fbpp, fast_path);
		}

		XImage *img = XGetImage(dpy, root, 0, 0, scr_w, scr_h, AllPlanes, ZPixmap);
		if (!img) { usleep(200000); continue; }
		memcpy(fb, img->data, (size_t)scr_w * scr_h * 4);
		XDestroyImage(img);

		/* fast path: 1:1 with RGB565 */
		if (fast_path && scr_w == (int)var.xres && scr_h == (int)var.yres) {
			copy_1to1_rgb565((uint16_t *)panel, fb, scr_w, scr_h, var.xres);
		} else {
			box_filter_generic(panel, fb, scr_w, scr_h, &var);
		}

		/* sync to trigger kernel DMA (msync is ~300µs, fast) */
		msync(panel, fbsize, MS_SYNC);

		frame++;
		gettimeofday(&t_now, 0);
		long dt = (t_now.tv_sec - t_last.tv_sec) * 1000
			+ (t_now.tv_usec - t_last.tv_usec) / 1000;
		t_frame_avg = (t_frame_avg * 255 + dt) / 256;
		t_last = t_now;

		if ((frame & 0x3f) == 0)
			fprintf(stderr, "spi-mirror: frame %u avg-fps=%.1f\n",
				frame, 1000.0 / (t_frame_avg ? t_frame_avg : 1));
	}
	return 0;
}