#!/usr/bin/env python3
"""Convert XWD (X Window Dump) to PNG. Handles the big-endian header format."""
import struct, sys
from PIL import Image

def parse_xwd(path):
    with open(path, 'rb') as f:
        data = f.read()
    # XWD header is big-endian (X11 network byte order)
    (header_size, version, pixmap_format, depth, width, height,
     xoffset, byte_order, bitmap_unit, bitmap_bit_order, bitmap_pad,
     bits_per_pixel, bytes_per_line, visual_class,
     red_mask, green_mask, blue_mask,
     bits_per_rgb, colormap_entries, ncolors) = struct.unpack('>IIIIIIIIIIIIIIIIIIII', data[:80])
    # window info follows (5 u32) but we don't need it
    print(f"hdr={header_size} ver={version} fmt={pixmap_format} depth={depth} {width}x{height} bpp={bits_per_pixel} bpl={bytes_per_line}")
    # Skip colormap if present
    off = header_size
    if ncolors > 0:
        # each color: 4 bytes (pixel) + 2 (flags) + 2 (pad) + 2*2 (red/green/blue 16-bit) = 12 bytes
        off += ncolors * 12
    imgdata = data[off:off + height * bytes_per_line]
    if bits_per_pixel == 32:
        mode = 'RGBA'
        img = Image.frombytes('RGBA', (width, height), imgdata, 'raw', 'BGRA', 0, 1)
    elif bits_per_pixel == 24:
        mode = 'RGB'
        img = Image.frombytes('RGB', (width, height), imgdata, 'raw', 'BGR', 0, 1)
    elif bits_per_pixel == 16:
        mode = 'RGB'
        # 16bpp RGB565 -> expand manually
        arr = bytearray(imgdata)
        out = bytearray(width * height * 3)
        for i in range(width * height):
            v = struct.unpack_from('>H' if byte_order == 0 else '<H', imgdata, i*2)[0]
            r = (v >> 11) & 0x1F
            g = (v >> 5) & 0x3F
            b = v & 0x1F
            out[i*3] = (r << 3) | (r >> 2)
            out[i*3+1] = (g << 2) | (g >> 4)
            out[i*3+2] = (b << 3) | (b >> 2)
        img = Image.frombytes('RGB', (width, height), bytes(out))
    else:
        raise ValueError(f"unsupported bpp {bits_per_pixel}")
    return img

if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    img = parse_xwd(src)
    img.save(dst)
    print(f"Saved {dst} {img.size} {img.mode}")
