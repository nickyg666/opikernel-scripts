#!/usr/bin/env python3
"""Generate 192x192 middle-finger logo PNG."""
from PIL import Image, ImageDraw, ImageFont
import glob

S = 4  # supersample
W = H = 192 * S
img = Image.new("RGBA", (W, H), (10, 10, 14, 255))
d = ImageDraw.Draw(img)

skin = (240, 178, 130, 255)
dark = (198, 134, 92, 255)

# fist (rounded block)
fx0, fy0, fx1, fy1 = int(W*0.24), int(H*0.42), int(W*0.76), int(H*0.88)
d.rounded_rectangle([fx0, fy0, fx1, fy1], radius=int(18*S), fill=skin)
# knuckle lines
for i, x in enumerate([0.36, 0.5, 0.64]):
    d.line([(W*x, fy0+int(8*S)), (W*x, fy0+int(22*S))], fill=dark, width=int(3*S))
# thumb across front
d.rounded_rectangle([fx0-int(6*S), int(H*0.60), int(W*0.44), int(H*0.72)],
                    radius=int(10*S), fill=skin, outline=dark, width=int(2*S))
# middle finger (up)
mx0, mx1 = int(W*0.42), int(W*0.58)
my0, my1 = int(H*0.08), int(H*0.50)
d.rounded_rectangle([mx0, my0, mx1, my1], radius=int(13*S), fill=skin)
# fingernail
nw, nh = int(9*S), int(7*S)
d.rounded_rectangle([int(W*0.5-nw/2), my0+int(4*S), int(W*0.5+nw/2), my0+int(4*S)+nh],
                    radius=int(3*S), fill=(250, 228, 210, 255))
# wrist
d.rounded_rectangle([int(W*0.38), int(H*0.84), int(W*0.62), int(H)], radius=int(6*S), fill=skin)

img = img.resize((192, 192), Image.LANCZOS)
img.save("/home/host/opikernel/shots/fu-logo-192.png")
print("saved", img.size)
