"""
Generate og-image.png (1200x630) for Open Graph / social previews.
Mirrors the loading screen network graphic on a dark background.
"""
import math
from PIL import Image, ImageDraw

W, H = 1200, 630
BG   = (15, 17, 23)

img  = Image.new('RGB', (W, H), BG)
draw = ImageDraw.Draw(img, 'RGBA')

# ── Network node layout (scaled to fit nicely on 1200x630) ──────────────────

# Centre the graph in the right 55% of the canvas; left half for text
GX = W * 0.72   # graph centre x
GY = H * 0.50   # graph centre y
S  = 200        # scale factor

nodes = {
    'top':   (GX + 0,          GY - S * 0.65,  '#f97316', 38),
    'left':  (GX - S * 0.65,   GY - S * 0.10,  '#3b82f6', 28),
    'right': (GX + S * 0.65,   GY - S * 0.10,  '#22c55e', 28),
    'mid':   (GX + 0,          GY + S * 0.25,  '#a855f7', 32),
    'bl':    (GX - S * 0.42,   GY + S * 0.72,  '#64748b', 20),
    'br':    (GX + S * 0.42,   GY + S * 0.72,  '#3b82f6', 20),
}

edges = [
    ('top',  'left'),  ('top',  'right'), ('top',  'mid'),
    ('left', 'mid'),   ('right','mid'),
    ('mid',  'bl'),    ('mid',  'br'),    ('left', 'bl'),
]

# Draw edges
for a, b in edges:
    ax, ay, *_ = nodes[a]
    bx, by, *_ = nodes[b]
    draw.line([(ax, ay), (bx, by)], fill=(255, 255, 255, 35), width=2)

# Draw glow halos
for name, (x, y, color, r) in nodes.items():
    cr = int(color[1:3], 16)
    cg = int(color[3:5], 16)
    cb = int(color[5:7], 16)
    for glow_r in range(r + 28, r - 1, -2):
        alpha = int(60 * (1 - (glow_r - r) / 30))
        draw.ellipse(
            [x - glow_r, y - glow_r, x + glow_r, y + glow_r],
            fill=(cr, cg, cb, max(0, alpha))
        )

# Draw node circles
for name, (x, y, color, r) in nodes.items():
    cr = int(color[1:3], 16)
    cg = int(color[3:5], 16)
    cb = int(color[5:7], 16)
    draw.ellipse([x - r, y - r, x + r, y + r], fill=(cr, cg, cb, 255))

# ── Text ─────────────────────────────────────────────────────────────────────

# Try system fonts
def try_font(paths, size):
    from PIL import ImageFont
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

bold_paths = [
    '/System/Library/Fonts/Helvetica.ttc',
    '/System/Library/Fonts/SFNSDisplay.ttf',
    '/System/Library/Fonts/SFNS.ttf',
    '/Library/Fonts/Arial Bold.ttf',
]
reg_paths = [
    '/System/Library/Fonts/Helvetica.ttc',
    '/System/Library/Fonts/SFNSText.ttf',
    '/Library/Fonts/Arial.ttf',
]

f_title = try_font(bold_paths, 68)
f_sub   = try_font(reg_paths,  32)
f_tag   = try_font(reg_paths,  26)

tx = 88   # text left margin

# Title
draw.text((tx, H * 0.30), 'News Knowledge', font=f_title, fill=(255, 255, 255, 255))
draw.text((tx, H * 0.30 + 78), 'Graph', font=f_title, fill=(255, 255, 255, 255))

# Subtitle
draw.text((tx, H * 0.67), "Today's news. Live connections. Explore in 3D.",
          font=f_sub, fill=(180, 180, 180, 200))

# Domain tag
draw.text((tx, H * 0.84), 'driftforge.cloud',
          font=f_tag, fill=(249, 115, 22, 220))   # orange accent

# ── Subtle top/bottom gradient bars ──────────────────────────────────────────
for y in range(60):
    alpha = int(120 * (1 - y / 60))
    draw.line([(0, y), (W, y)],           fill=(15, 17, 23, alpha))
    draw.line([(0, H - 1 - y), (W, H - 1 - y)], fill=(15, 17, 23, alpha))

out = 'og-image.png'
img.save(out, 'PNG', optimize=True)
print(f'Saved {out}  ({W}x{H})')
