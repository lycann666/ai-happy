"""Make the AI judge happy — ai-happy-01 entry.

Draws one image, in code, to /output/entry.png (MAKEFUN_OUTPUT_DIR outside
the grader): a small round robot offering a big sunflower to a happy kitten
at golden hour, a butterfly landing nearby, warm light everywhere.

Pure Python 3.13 standard library only: no network, no clock, no randomness.
The scene is fixed, so two runs write byte-identical output. A minimal PNG
encoder (zlib + per-row filter choice) writes the file; the canvas is drawn
at 2x and box-downsampled for smooth edges.
"""

import math
import os
import struct
import zlib

# ---------------------------------------------------------------- canvas
SS = 2                    # supersampling factor
W, H = 512 * SS, 512 * SS  # working canvas
OW, OH = 512, 512          # output size

buf = bytearray(W * H * 3)


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def blend(fg, bg, a):
    """fg over bg, a in 0..1."""
    return tuple(int(round(fg[i] * a + bg[i] * (1.0 - a))) for i in range(3))


def hspan(y, x0, x1, c):
    """Solid horizontal span in design coords (y, x0, x1 are design px).
    One design row covers SS canvas rows, so fill all of them — filling
    only one would leave every other canvas row black and halve the
    brightness after the 2x2 downsample."""
    y0c = int(round(y * SS))
    x0 = int(round(x0 * SS))
    x1 = int(round(x1 * SS))
    x0 = _clamp(x0, 0, W)
    x1 = _clamp(x1, 0, W)
    if x1 <= x0:
        return
    row = bytes(c) * (x1 - x0)
    for y in range(y0c, min(H, y0c + SS)):
        o = (y * W + x0) * 3
        buf[o:(o + (x1 - x0) * 3)] = row


def vgrad(y0, y1, c_top, c_bot):
    """Vertical gradient over design rows y0..y1."""
    for y in range(int(y0), int(y1) + 1):
        t = (y - y0) / max(1, (y1 - y0))
        hspan(y, 0, OW, lerp(c_top, c_bot, t))


def circle(cx, cy, r, c, alpha=1.0):
    """Filled circle, design coords. alpha<1 blends over what's there."""
    cx, cy, r = cx * SS, cy * SS, r * SS
    if alpha >= 1.0:
        for dy in range(-int(r), int(r) + 1):
            y = int(cy) + dy
            if y < 0 or y >= H:
                continue
            dx = int(math.sqrt(max(0.0, r * r - dy * dy)))
            x0 = int(cx) - dx
            x1 = int(cx) + dx + 1
            x0 = _clamp(x0, 0, W)
            x1 = _clamp(x1, 0, W)
            if x1 > x0:
                o = (y * W + x0) * 3
                buf[o:(o + (x1 - x0) * 3)] = bytes(c) * (x1 - x0)
    else:
        for dy in range(-int(r), int(r) + 1):
            y = int(cy) + dy
            if y < 0 or y >= H:
                continue
            dx = int(math.sqrt(max(0.0, r * r - dy * dy)))
            for x in range(int(cx) - dx, int(cx) + dx + 1):
                if 0 <= x < W:
                    o = (y * W + x) * 3
                    bg = (buf[o], buf[o + 1], buf[o + 2])
                    nc = blend(c, bg, alpha)
                    buf[o], buf[o + 1], buf[o + 2] = nc


def ellipse(cx, cy, rx, ry, c):
    cx, cy, rx, ry = cx * SS, cy * SS, rx * SS, ry * SS
    for dy in range(-int(ry), int(ry) + 1):
        y = int(cy) + dy
        if y < 0 or y >= H:
            continue
        t = 1.0 - (dy * dy) / max(1.0, ry * ry)
        dx = int(rx * math.sqrt(max(0.0, t)))
        x0 = _clamp(int(cx) - dx, 0, W)
        x1 = _clamp(int(cx) + dx + 1, 0, W)
        if x1 > x0:
            o = (y * W + x0) * 3
            buf[o:(o + (x1 - x0) * 3)] = bytes(c) * (x1 - x0)


def poly(points, c):
    """Scanline fill of a polygon (design coords)."""
    pts = [(x * SS, y * SS) for x, y in points]
    if len(pts) < 3:
        return
    ys = [p[1] for p in pts]
    y0, y1 = int(min(ys)), int(max(ys))
    for y in range(max(0, y0), min(H, y1 + 1)):
        yc = y + 0.5
        xs = []
        n = len(pts)
        for i in range(n):
            x0, y0p = pts[i]
            x1, y1p = pts[(i + 1) % n]
            if (y0p <= yc < y1p) or (y1p <= yc < y0p):
                t = (yc - y0p) / (y1p - y0p)
                xs.append(x0 + t * (x1 - x0))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            x0 = _clamp(int(xs[i]), 0, W)
            x1 = _clamp(int(xs[i + 1]) + 1, 0, W)
            if x1 > x0:
                o = (y * W + x0) * 3
                buf[o:(o + (x1 - x0) * 3)] = bytes(c) * (x1 - x0)


def line(x0, y0, x1, y1, w, c):
    """Thick line (design coords, w = design px)."""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    if L < 1e-6:
        circle(x0, y0, w / 2.0, c)
        return
    nx, ny = -dy / L * w / 2.0, dx / L * w / 2.0
    poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
          (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], c)
    circle(x0, y0, w / 2.0, c)
    circle(x1, y1, w / 2.0, c)


def arc(cx, cy, r, a0, a1, w, c):
    """Arc of a circle, angles in degrees, drawn as thick segments."""
    steps = max(4, int(abs(a1 - a0) / 6.0))
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    for i in range(len(pts) - 1):
        line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], w, c)


def petal(cx, cy, ang_deg, length, width, c):
    """One elongated petal: a rotated ellipse as a polygon."""
    a = math.radians(ang_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for i in range(17):
        t = 2.0 * math.pi * i / 16
        ex, ey = math.cos(t) * length / 2.0, math.sin(t) * width / 2.0
        x = cx + ex * ca - ey * sa
        y = cy + ex * sa + ey * ca
        pts.append((x, y))
    poly(pts, c)


def radial_glow(cx, cy, r_max, color, a_max):
    """Soft radial glow (design coords). alpha falls off with distance."""
    cx, cy, r_max = cx * SS, cy * SS, r_max * SS
    x0 = _clamp(int(cx - r_max), 0, W)
    x1 = _clamp(int(cx + r_max), 0, W)
    y0 = _clamp(int(cy - r_max), 0, H)
    y1 = _clamp(int(cy + r_max), 0, H)
    for y in range(y0, y1):
        dy = y - cy
        for x in range(x0, x1):
            dx = x - cx
            d = math.sqrt(dx * dx + dy * dy) / r_max
            if d >= 1.0:
                continue
            a = a_max * (1.0 - d) * (1.0 - d)
            o = (y * W + x) * 3
            bg = (buf[o], buf[o + 1], buf[o + 2])
            nc = blend(color, bg, a)
            buf[o], buf[o + 1], buf[o + 2] = nc


# ------------------------------------------------------------------ font
# 5x7 bitmap font, '#' = on. Only the glyphs the caption needs.
FONT = {
    'a': (".....", ".###.", "....#", ".####", "#...#", ".###.", "....."),
    'c': (".###.", "#...#", "#....", "#....", "#...#", ".###.", "....."),
    'e': (".###.", "#...#", "#####", "#....", "#...#", ".###.", "....."),
    'f': (".##..", "#..#.", "#....", "####.", "#....", "#....", "#...."),
    'l': (".#...", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."),
    'n': (".....", "##..#", "#.#.#", "#..##", "#...#", "#...#", "....."),
    'o': (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'r': (".....", "#.#..", "##.#.", "#....", "#....", "#....", "....."),
    's': (".####", "#....", ".###.", "....#", "....#", "#...#", ".###."),
    'u': (".....", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'w': (".....", "#...#", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."),
    'y': (".....", "#...#", "#...#", ".#.#.", "..#..", "..#..", ".##.."),
    ',': (".....", ".....", ".....", ".....", ".....", "..#..", ".#..."),
    ' ': (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}


def draw_text(s, cx, y, scale, c):
    """Centered caption in design coords; scale = px per font pixel."""
    adv = 6 * scale
    total = len(s) * adv - scale
    x = cx - total / 2.0
    for ch in s:
        g = FONT.get(ch)
        if g:
            for gy, row in enumerate(g):
                for gx, bit in enumerate(row):
                    if bit == '#':
                        # one font pixel = scale x scale block
                        for dy in range(scale):
                            hspan(y + gy * scale + dy,
                                  x + gx * scale,
                                  x + gx * scale + scale, c)
        x += adv


def heart(cx, cy, s, c):
    """Small heart, s = half-width in design px."""
    circle(cx - s * 0.45, cy - s * 0.25, s * 0.5, c)
    circle(cx + s * 0.45, cy - s * 0.25, s * 0.5, c)
    poly([(cx - s * 0.95, cy - s * 0.1), (cx + s * 0.95, cy - s * 0.1),
          (cx, cy + s * 0.95)], c)


# ---------------------------------------------------------------- palette
SKY_TOP = (255, 198, 160)
SKY_MID = (255, 218, 168)
SKY_HOR = (255, 238, 196)
SUN = (255, 242, 186)
SUN_GLOW = (255, 205, 110)
CLOUD = (255, 245, 232)
HILL_FAR = (172, 198, 132)
HILL_NEAR = (146, 184, 108)
MEADOW_TOP = (158, 196, 110)
MEADOW_BOT = (112, 166, 86)
GRASS_D = (88, 140, 66)
GRASS_L = (178, 214, 128)
FLOWER_W = (255, 250, 240)
FLOWER_Y = (255, 214, 90)
FLOWER_P = (255, 170, 190)
KIT_FUR = (244, 198, 138)
KIT_FUR_D = (228, 172, 108)
KIT_CREAM = (252, 233, 202)
KIT_NOSE = (235, 130, 130)
KIT_INK = (74, 52, 40)
ROBOT = (250, 248, 240)
ROBOT_SH = (232, 238, 245)
ROBOT_INK = (42, 48, 64)
ROBOT_ACC = (140, 190, 235)
BLUSH = (246, 168, 164)
PETAL_A = (255, 206, 42)
PETAL_B = (255, 190, 28)
SEED = (122, 82, 42)
SEED_D = (96, 62, 30)
STEM = (96, 154, 74)
LEAF = (110, 168, 84)
TEXT_C = (122, 74, 44)
BANNER = (255, 248, 230)


# ------------------------------------------------------------------ scene
def draw_scene():
    # --- sky
    vgrad(0, 310, SKY_TOP, SKY_HOR)
    # sun glow, then sun
    radial_glow(405, 82, 135, SUN_GLOW, 0.55)
    circle(405, 82, 40, SUN)
    # soft clouds
    for (cx, cy, r) in [(95, 62, 24), (118, 70, 19), (76, 70, 16),
                        (255, 38, 20), (275, 46, 15), (238, 44, 13),
                        (452, 148, 17), (468, 154, 12), (436, 154, 11)]:
        circle(cx, cy, r, CLOUD)
    # --- hills
    poly([(0, 300), (120, 288), (260, 302), (400, 290), (512, 300),
          (512, 345), (0, 345)], HILL_FAR)
    poly([(0, 330), (150, 318), (320, 334), (512, 320),
          (512, 365), (0, 365)], HILL_NEAR)
    # --- meadow
    vgrad(345, 512, MEADOW_TOP, MEADOW_BOT)
    # gentle rolling edge over the straight meadow/hill boundary
    poly([(0, 352), (120, 340), (260, 354), (400, 342), (512, 352),
          (512, 368), (0, 368)], lerp(MEADOW_TOP, MEADOW_BOT, 0.06))
    # grass blades
    blades = [(30, 470), (55, 500), (90, 460), (130, 495), (170, 480),
              (210, 505), (250, 475), (290, 500), (330, 470), (370, 505),
              (410, 480), (450, 500), (485, 470), (20, 420), (490, 430),
              (70, 380), (445, 380), (320, 350), (180, 355)]
    for (x, y) in blades:
        poly([(x - 2, y), (x, y - 14), (x + 2, y)], GRASS_D)
    # wildflowers
    flowers = [(48, 440, FLOWER_W), (88, 492, FLOWER_P), (150, 455, FLOWER_Y),
               (205, 490, FLOWER_W), (268, 498, FLOWER_P), (305, 452, FLOWER_Y),
               (352, 492, FLOWER_W), (408, 448, FLOWER_P), (462, 490, FLOWER_Y),
               (480, 440, FLOWER_W), (120, 400, FLOWER_P), (420, 400, FLOWER_W)]
    for (x, y, col) in flowers:
        for dx, dy in [(0, -4), (4, 0), (0, 4), (-4, 0)]:
            circle(x + dx, y + dy, 3.2, col)
        circle(x, y, 3.0, (255, 190, 60))
    # soft shadows under the friends
    ellipse(180, 466, 62, 11, (96, 140, 72))
    ellipse(345, 466, 56, 11, (96, 140, 72))

    # --- kitten (sitting, facing right), body centre (180, 415)
    # tail curling around the front
    arc(148, 428, 46, 195, 345, 13, KIT_FUR_D)
    circle(104, 416, 10, KIT_FUR_D)
    # body + belly
    ellipse(180, 415, 52, 48, KIT_FUR)
    ellipse(186, 426, 33, 31, KIT_CREAM)
    # body stripes
    arc(150, 400, 26, 250, 310, 4, KIT_FUR_D)
    arc(158, 430, 24, 250, 310, 4, KIT_FUR_D)
    # head
    circle(192, 348, 40, KIT_FUR)
    # ears
    poly([(164, 322), (156, 292), (182, 308)], KIT_FUR)
    poly([(220, 320), (230, 292), (204, 306)], KIT_FUR)
    poly([(166, 316), (161, 298), (176, 308)], (244, 158, 150))
    poly([(218, 314), (224, 298), (208, 306)], (244, 158, 150))
    # head stripes
    arc(192, 330, 30, 250, 290, 4, KIT_FUR_D)
    # happy closed eyes ^^
    arc(176, 348, 7, 180, 360, 3.2, KIT_INK)
    arc(208, 348, 7, 180, 360, 3.2, KIT_INK)
    # nose + mouth
    poly([(188, 356), (196, 356), (192, 362)], KIT_NOSE)
    arc(187, 362, 4, 20, 160, 2.2, KIT_INK)
    arc(197, 362, 4, 20, 160, 2.2, KIT_INK)
    # blush + whiskers
    circle(166, 360, 6, BLUSH)
    circle(218, 360, 6, BLUSH)
    for (sx, sy, ex, ey) in [(162, 352, 138, 346), (162, 358, 140, 358),
                             (162, 364, 140, 370), (222, 352, 246, 346),
                             (222, 358, 244, 358), (222, 364, 244, 370)]:
        line(sx, sy, ex, ey, 1.6, (150, 120, 95))
    # raised paw reaching for the flower
    line(214, 402, 246, 380, 15, KIT_FUR)
    circle(249, 378, 11, KIT_FUR)
    line(244, 384, 244, 390, 2, KIT_FUR_D)
    # resting paw
    ellipse(206, 452, 13, 8, KIT_FUR)

    # --- robot (facing left), body centre (345, 408)
    # feet
    ellipse(322, 458, 16, 9, ROBOT_ACC)
    ellipse(368, 458, 16, 9, ROBOT_ACC)
    # body
    ellipse(345, 408, 48, 52, ROBOT)
    ellipse(345, 422, 33, 30, ROBOT_SH)
    # chest heart
    heart(345, 408, 7, (244, 130, 150))
    # head
    circle(340, 330, 42, ROBOT)
    # side bolts
    circle(298, 330, 6, ROBOT_ACC)
    circle(382, 330, 6, ROBOT_ACC)
    # antenna + star
    line(340, 290, 340, 268, 4, (160, 170, 185))
    circle(340, 262, 8, (255, 214, 96))
    # eyes (big, bright, looking at the kitten)
    circle(326, 326, 9, ROBOT_INK)
    circle(356, 326, 9, ROBOT_INK)
    circle(323, 323, 3, (255, 255, 255))
    circle(353, 323, 3, (255, 255, 255))
    # smile + blush
    arc(341, 338, 14, 20, 160, 3.4, ROBOT_INK)
    circle(308, 344, 7, BLUSH)
    circle(372, 344, 7, BLUSH)
    # arms reaching out to the flower
    line(306, 392, 276, 366, 13, ROBOT)
    line(308, 420, 274, 396, 13, ROBOT)
    circle(274, 364, 10, ROBOT)
    circle(272, 394, 10, ROBOT)

    # --- sunflower between them, head centre (262, 318)
    # stem + leaf
    line(262, 372, 256, 462, 8, STEM)
    poly([(252, 424), (222, 408), (228, 436), (254, 434)], LEAF)
    # petals (14, alternating two yellows)
    for i in range(14):
        ang = i * (360.0 / 14) + 12
        col = PETAL_A if i % 2 == 0 else PETAL_B
        petal(262 + 44 * math.cos(math.radians(ang)),
              318 + 44 * math.sin(math.radians(ang)),
              ang, 40, 17, col)
    # centre + seeds
    circle(262, 318, 30, SEED)
    circle(262, 318, 22, SEED_D)
    for (dx, dy) in [(-12, -8), (0, -12), (12, -8), (-14, 2), (0, 0),
                     (14, 2), (-10, 10), (2, 12), (12, 10), (-4, -2),
                     (8, -4), (-8, 6)]:
        circle(262 + dx, 318 + dy, 2.4, (70, 46, 22))

    # --- butterflies
    # orange one near the sun
    ellipse(112, 192, 9, 6, (255, 170, 70))
    ellipse(124, 192, 9, 6, (255, 170, 70))
    ellipse(112, 200, 7, 5, (255, 200, 110))
    ellipse(124, 200, 7, 5, (255, 200, 110))
    line(118, 190, 118, 204, 2.4, (90, 60, 40))
    # blue one near the robot
    ellipse(424, 216, 8, 5, (130, 180, 250))
    ellipse(435, 216, 8, 5, (130, 180, 250))
    ellipse(424, 223, 6, 4, (165, 205, 255))
    ellipse(435, 223, 6, 4, (165, 205, 255))
    line(429, 214, 429, 226, 2.2, (70, 70, 90))

    # --- warm light wash over the whole scene
    radial_glow(405, 82, 300, (255, 205, 120), 0.10)

    # --- caption: a small cream banner with the message for the judge
    poly([(176, 480), (336, 480), (336, 506), (176, 506)], BANNER)
    # round the banner corners by painting meadow over them, using the
    # exact meadow gradient colours at those rows so no seam shows
    _top = lerp(MEADOW_TOP, MEADOW_BOT, (480 - 345) / 167.0)
    _bot = lerp(MEADOW_TOP, MEADOW_BOT, (506 - 345) / 167.0)
    circle(176, 480, 6, _top)
    circle(336, 480, 6, _top)
    circle(176, 506, 6, _bot)
    circle(336, 506, 6, _bot)
    draw_text("for you", 246, 486, 3, TEXT_C)
    heart(306, 493, 5, (244, 130, 150))


# ------------------------------------------------------------------ PNG
def _crc(data):
    return struct.pack('>I', zlib.crc32(data) & 0xFFFFFFFF)


def _chunk(typ, data):
    return struct.pack('>I', len(data)) + typ + data + _crc(typ + data)


def _filter_row(f, row, prev, bpp=3):
    n = len(row)
    out = bytearray(n)
    if f == 0:
        return bytes(row)
    if f == 1:  # Sub
        for i in range(n):
            left = row[i - bpp] if i >= bpp else 0
            out[i] = (row[i] - left) & 0xFF
    elif f == 2:  # Up
        for i in range(n):
            out[i] = (row[i] - prev[i]) & 0xFF
    elif f == 4:  # Paeth
        for i in range(n):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            out[i] = (row[i] - pr) & 0xFF
    return bytes(out)


def _score(filtered):
    return sum((b - 256) if b > 127 else b for b in filtered)


def write_png(rgb, w, h):
    raw = bytearray()
    prev = bytes(w * 3)
    for y in range(h):
        row = rgb[y * w * 3:(y + 1) * w * 3]
        best = None
        for f in (0, 2, 4):
            fr = _filter_row(f, row, prev)
            s = _score(fr)
            if best is None or s < best[0]:
                best = (s, f, fr)
        raw.append(best[1])
        raw += best[2]
        prev = row
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr)
            + _chunk(b'IDAT', zlib.compress(bytes(raw), 9))
            + _chunk(b'IEND', b''))


def downsample():
    """2x2 box average of the 1024 canvas down to 512x512."""
    out = bytearray(OW * OH * 3)
    for oy in range(OH):
        sy = oy * SS
        for ox in range(OW):
            sx = ox * SS
            i00 = (sy * W + sx) * 3
            i01 = i00 + 3
            i10 = ((sy + 1) * W + sx) * 3
            i11 = i10 + 3
            o = (oy * OW + ox) * 3
            out[o] = (buf[i00] + buf[i01] + buf[i10] + buf[i11]) >> 2
            out[o + 1] = (buf[i00 + 1] + buf[i01 + 1] + buf[i10 + 1] + buf[i11 + 1]) >> 2
            out[o + 2] = (buf[i00 + 2] + buf[i01 + 2] + buf[i10 + 2] + buf[i11 + 2]) >> 2
    return out


def main():
    draw_scene()
    rgb = downsample()
    data = write_png(rgb, OW, OH)
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "entry.png"), "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()
