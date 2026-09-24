"""Generated placeholder artwork (seed.py) and wall backgrounds
(tools/make_walls.py), drawn with Pillow in the site's candy palette.
Replace the art through Admin -> Images and the walls by dropping real
photos over app/static/walls/*.jpg (keeping the file names), adjusting
each wall's `inches` in templates/_wall.html if the real photo covers a
different width of wall."""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

COBALT = (74, 109, 167)
PINK = (229, 98, 110)
YELLOW = (242, 181, 68)
CREAM = (251, 241, 231)
PEACH = (246, 206, 180)
BLUSH = (246, 184, 176)
SKY = (157, 180, 214)
GREY = (58, 57, 61)
MINT = (170, 208, 190)

W, H = 800, 1000  # 4:5, same as an 8x10 tile


def _stripes(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    band = rng.choice([70, 90, 110])
    for i, x in enumerate(range(-H, W + H, band)):
        color = fg[i % len(fg)]
        d.polygon([(x, 0), (x + band // 2, 0), (x + band // 2 + H, H), (x + H, H)], fill=color)


def _dots(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    step = rng.choice([100, 125])
    r = step * 0.3
    for row, y in enumerate(range(step // 2, H + step, step)):
        off = step // 2 if row % 2 else 0
        for col, x in enumerate(range(step // 2 - off, W + step, step)):
            d.ellipse([x - r, y - r, x + r, y + r], fill=fg[(row + col) % len(fg)])


def _jawbreaker(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    cx, cy = W / 2, H / 2
    colors = fg + bg[1:]
    for i, rad in enumerate(range(700, 0, -60)):
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=colors[i % len(colors)])


def _checker(d, fg, bg, rng):
    s = 200
    for r in range(0, H // s + 1):
        for c in range(0, W // s + 1):
            color = fg[(r + c) % len(fg)] if (r + c) % 2 == 0 else bg[0]
            d.rectangle([c * s, r * s, c * s + s, r * s + s], fill=color)
    for r in range(0, H // s + 1):
        for c in range(0, W // s + 1):
            if (r + c) % 2:
                x, y = c * s + s / 2, r * s + s / 2
                d.ellipse([x - 30, y - 30, x + 30, y + 30], fill=fg[-1])


def _waves(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    amp, period, thick = 45, rng.choice([260, 320]), 70
    for i, base in enumerate(range(-40, H + 100, thick + 30)):
        pts = [(x, base + amp * math.sin((x / period) * 2 * math.pi + i * 0.9)) for x in range(-10, W + 20, 10)]
        d.line(pts, fill=fg[i % len(fg)], width=thick, joint="curve")


def _triangles(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    s = 200
    for r in range(0, H // s + 1):
        for c in range(0, W // s + 1):
            x, y = c * s, r * s
            color = fg[rng.randrange(len(fg))]
            if rng.random() < 0.5:
                d.polygon([(x, y), (x + s, y), (x, y + s)], fill=color)
            else:
                d.polygon([(x + s, y), (x + s, y + s), (x, y + s)], fill=color)


def _arches(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    cx, base = W / 2, H * 0.78
    colors = fg + [bg[0]]
    for i, rad in enumerate(range(360, 40, -55)):
        d.pieslice([cx - rad, base - rad, cx + rad, base + rad], 180, 360, fill=colors[i % len(colors)])
    d.rectangle([0, base, W, H], fill=fg[0])


def _bloom(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    for (cx, cy, size) in [(W * 0.5, H * 0.45, 230), (W * 0.15, H * 0.12, 90), (W * 0.85, H * 0.88, 110)]:
        petals = 8
        for k in range(petals):
            a = 2 * math.pi * k / petals
            px, py = cx + math.cos(a) * size * 0.62, cy + math.sin(a) * size * 0.62
            r = size * 0.42
            d.ellipse([px - r, py - r, px + r, py + r], fill=fg[k % 2])
        r = size * 0.36
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg[-1])


def _scallops(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    s = 160
    for row, y in enumerate(range(H + s, -s, -s // 2)):
        off = s // 2 if row % 2 else 0
        for x in range(-off, W + s, s):
            color = fg[row % len(fg)]
            d.ellipse([x, y - s // 2, x + s, y + s // 2], fill=color, outline=bg[0], width=8)


def _sun(d, fg, bg, rng):
    d.rectangle([0, 0, W, H], fill=bg[0])
    cx, cy = W / 2, H / 2
    rays = 16
    for k in range(rays):
        a0 = 2 * math.pi * k / rays
        a1 = a0 + math.pi / rays
        d.polygon([(cx, cy), (cx + 900 * math.cos(a0), cy + 900 * math.sin(a0)),
                   (cx + 900 * math.cos(a1), cy + 900 * math.sin(a1))], fill=fg[k % 2])
    r = 170
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg[-1])


# (title, pattern, foreground colors, background colors, categories)
PLACEHOLDER_ART = [
    ("Taffy Stripe", _stripes, [PINK, CREAM], [YELLOW], ["Stripes"]),
    ("Blueberry Stripe", _stripes, [COBALT, SKY], [CREAM], ["Stripes"]),
    ("Gumdrop Dots", _dots, [PINK, YELLOW, COBALT], [CREAM], ["Dots & Circles"]),
    ("Lemon Drops", _dots, [YELLOW], [COBALT], ["Dots & Circles"]),
    ("Jawbreaker", _jawbreaker, [PINK, YELLOW, COBALT, CREAM], [BLUSH], ["Dots & Circles"]),
    ("Checkerboard Fudge", _checker, [COBALT, PINK], [CREAM], ["Geometric"]),
    ("Ribbon Candy", _waves, [PINK, YELLOW, COBALT], [CREAM], ["Stripes"]),
    ("Sea Glass Waves", _waves, [SKY, MINT, COBALT], [CREAM], ["Stripes"]),
    ("Candy Corn Shards", _triangles, [YELLOW, PINK, CREAM, COBALT], [PEACH], ["Geometric"]),
    ("Rainbow Drop", _arches, [COBALT, PINK, YELLOW, SKY], [CREAM], ["Geometric"]),
    ("Sugar Bloom", _bloom, [PINK, BLUSH, YELLOW], [CREAM], ["Florals"]),
    ("Midnight Bloom", _bloom, [SKY, CREAM, YELLOW], [COBALT], ["Florals"]),
    ("Scallop Shell", _scallops, [PINK, BLUSH, PEACH], [CREAM], ["Geometric"]),
    ("Blue Scales", _scallops, [COBALT, SKY], [CREAM], ["Geometric"]),
    ("Lemon Sun", _sun, [YELLOW, CREAM, PINK], [CREAM], ["Florals"]),
    ("Cobalt Sun", _sun, [COBALT, SKY, YELLOW], [CREAM], ["Florals"]),
]


def make_art(pattern, fg, bg, seed):
    rng = random.Random(seed)
    img = Image.new("RGB", (W, H), bg[0])
    pattern(ImageDraw.Draw(img), fg, bg, rng)
    # A soft paper-ish grain so they read as art prints, not flat vectors.
    noise = Image.effect_noise((W, H), 14).convert("L").filter(ImageFilter.GaussianBlur(0.6))
    return Image.blend(img, Image.merge("RGB", (noise, noise, noise)), 0.05)


# --- walls -------------------------------------------------------------------

WALL_W, WALL_H = 1800, 1200


def _wall_base(color, floor_color, floor_y):
    img = Image.new("RGB", (WALL_W, WALL_H), color)
    d = ImageDraw.Draw(img)
    # gentle vertical light falloff
    for y in range(floor_y):
        shade = 1 - 0.07 * (y / floor_y)
        d.line([(0, y), (WALL_W, y)], fill=tuple(int(c * shade) for c in color))
    d.rectangle([0, floor_y, WALL_W, WALL_H], fill=floor_color)
    for x in range(0, WALL_W, 150):  # floorboards
        d.line([(x, floor_y), (x - 60, WALL_H)], fill=tuple(max(0, c - 18) for c in floor_color), width=3)
    d.rectangle([0, floor_y - 34, WALL_W, floor_y], fill=(250, 247, 242))  # baseboard
    d.line([(0, floor_y), (WALL_W, floor_y)], fill=(215, 205, 195), width=3)
    return img, d


def make_wall_painted():
    img, _ = _wall_base((236, 226, 214), (176, 138, 104), 1020)
    return img


def make_wall_sofa():
    img, d = _wall_base((222, 230, 226), (160, 124, 94), 1040)
    ppi = WALL_W / 168  # this picture covers 168 inches of wall
    sofa_w, sofa_h = 84 * ppi, 34 * ppi
    x0 = (WALL_W - sofa_w) / 2
    y1 = 1040 - 4 * ppi
    body = (74, 109, 167)
    d.rounded_rectangle([x0, y1 - sofa_h, x0 + sofa_w, y1 - 6 * ppi], radius=int(4 * ppi), fill=body)
    d.rounded_rectangle([x0 - 4 * ppi, y1 - sofa_h * 0.72, x0 + 7 * ppi, y1 - 4 * ppi], radius=int(3 * ppi), fill=(64, 96, 150))
    d.rounded_rectangle([x0 + sofa_w - 7 * ppi, y1 - sofa_h * 0.72, x0 + sofa_w + 4 * ppi, y1 - 4 * ppi], radius=int(3 * ppi), fill=(64, 96, 150))
    d.rounded_rectangle([x0 + 6 * ppi, y1 - sofa_h * 0.48, x0 + sofa_w - 6 * ppi, y1 - 7 * ppi], radius=int(2 * ppi), fill=(88, 124, 180))
    for fx in (x0 + 6 * ppi, x0 + sofa_w - 8 * ppi):
        d.rectangle([fx, y1 - 6 * ppi, fx + 2 * ppi, y1], fill=(90, 70, 50))
    for i, color in enumerate([(229, 98, 110), (242, 181, 68)]):  # cushions
        cx = x0 + sofa_w * (0.22 + 0.56 * i)
        d.rounded_rectangle([cx - 8 * ppi, y1 - sofa_h * 0.78, cx + 8 * ppi, y1 - sofa_h * 0.44], radius=int(3 * ppi), fill=color)
    return img.filter(ImageFilter.GaussianBlur(0.8))


def make_wall_entry():
    img, d = _wall_base((243, 222, 206), (150, 112, 84), 1030)
    ppi = WALL_W / 144
    tw, top = 48 * ppi, 1030 - 32 * ppi
    x0 = (WALL_W - tw) / 2
    wood = (120, 86, 60)
    d.rectangle([x0, top, x0 + tw, top + 2 * ppi], fill=wood)
    for lx in (x0 + 2 * ppi, x0 + tw - 3.5 * ppi):
        d.rectangle([lx, top, lx + 1.5 * ppi, 1030], fill=wood)
    d.rectangle([x0 + 2 * ppi, top + 12 * ppi, x0 + tw - 2 * ppi, top + 13 * ppi], fill=wood)
    # lamp
    lx = x0 + 5 * ppi
    d.rectangle([lx - 0.6 * ppi, top - 16 * ppi, lx + 0.6 * ppi, top], fill=(70, 70, 70))
    d.polygon([(lx - 6 * ppi, top - 16 * ppi), (lx + 6 * ppi, top - 16 * ppi), (lx + 4 * ppi, top - 25 * ppi), (lx - 4 * ppi, top - 25 * ppi)],
              fill=(250, 240, 220))
    # vase + stems
    vx = x0 + tw - 6 * ppi
    d.ellipse([vx - 3 * ppi, top - 9 * ppi, vx + 3 * ppi, top], fill=(229, 98, 110))
    for a in (-0.5, 0, 0.45):
        ex, ey = vx + math.sin(a) * 9 * ppi, top - 9 * ppi - math.cos(a) * 12 * ppi
        d.line([(vx, top - 8 * ppi), (ex, ey)], fill=(96, 140, 110), width=5)
        d.ellipse([ex - 1.6 * ppi, ey - 1.6 * ppi, ex + 1.6 * ppi, ey + 1.6 * ppi], fill=(242, 181, 68))
    return img.filter(ImageFilter.GaussianBlur(0.8))
