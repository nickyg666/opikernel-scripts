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
	Window root = DefaultRootWindow(dpy);

	int fd = open("/dev/fb-lcd", O_RDWR);
	if (fd < 0) {
		perror("spi-mirror: open /dev/fb-lcd");
		return 1;
	}
	struct fb_var_screeninfo var = {0};
	if (ioctl(fd, FBIOGET_VSCREENINFO, &var) < 0) {
		perror("FBIOGET_VSCREENINFO");
		return 1;
	}
	unsigned int fbpp = var.bits_per_pixel ? var.bits_per_pixel : 16;
	unsigned int fbbits = fbpp / 8;
	size_t fbsize = (size_t)var.xres * var.yres * fbbits;
	uint8_t *panel = mmap(NULL, fbsize, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (panel == MAP_FAILED) {
		perror("mmap fb");
		return 1;
	}

	int scr_w = 0, scr_h = 0;
	uint32_t *fb = NULL;

	unsigned frame = 0;
	for (;;) {
		XWindowAttributes wa;
		if (!XGetWindowAttributes(dpy, root, &wa)) {
			sleep(2);
			continue;
		}
		if (wa.width != scr_w || wa.height != scr_h) {
			uint32_t *nf = realloc(fb, (size_t)wa.width * wa.height * 4);
			if (!nf) {
				sleep(2);
				continue;
			}
			fb = nf;
			scr_w = wa.width;
			scr_h = wa.height;
			fprintf(stderr, "spi-mirror: %s %dx%d -> panel %dx%d (%ubpp)\n",
				disp, scr_w, scr_h, var.xres, var.yres, fbpp);
		}

		XImage *img = XGetImage(dpy, root, 0, 0, scr_w, scr_h, AllPlanes, ZPixmap);
		if (!img) {
			fprintf(stderr, "XGetImage failed\n");
			sleep(2);
			continue;
		}
		memcpy(fb, img->data, (size_t)scr_w * scr_h * 4);
		XDestroyImage(img);

		/* box-filter scr_w x scr_h -> panel size; pack per fb format */
		for (int y = 0; y < (int)var.yres; y++) {
			int y0 = y * scr_h / (int)var.yres;
			int y1 = (y + 1) * scr_h / (int)var.yres;
			if (y1 <= y0) y1 = y0 + 1;
			uint8_t *row = panel + (size_t)y * var.xres * fbbits;
			for (int x = 0; x < (int)var.xres; x++) {
				int x0 = x * scr_w / (int)var.xres;
				int x1 = (x + 1) * scr_w / (int)var.xres;
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
					   &var.red, &var.green, &var.blue);
			}
		}

		if ((frame++ & 0x1f) == 0)
			fprintf(stderr, "spi-mirror: frame %u pushed\n", frame);
		usleep(100000);
	}
	return 0;
}