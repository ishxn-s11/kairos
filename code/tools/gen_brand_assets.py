"""Generate KAIROS brand assets: favicon.ico (16/32/48), favicon PNGs (32/180/192/512),
and a 1200x630 og-image matching the site's monochrome technical aesthetic.
Black square, white K monogram + terminal dot, IBM Plex Mono (Consolas fallback)."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
IMG = FRONTEND / "assets" / "img"
IMG.mkdir(parents=True, exist_ok=True)

BOLD = "C:/Windows/Fonts/consolab.ttf"


def draw_k(size: int) -> Image.Image:
    im = Image.new("RGB", (size, size), "#050505")
    d = ImageDraw.Draw(im)
    # hairline frame, like the site's technical drawing language
    m = max(1, size // 32)
    d.rectangle([m, m, size - m, size - m], outline="#2a2a2a", width=max(1, size // 128))
    # K monogram + accent dot
    font = ImageFont.truetype(BOLD, int(size * 0.62))
    text = "K"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - size * 0.02),
           text, font=font, fill="#ffffff")
    dot_r = max(2, int(size * 0.045))
    d.ellipse([size - m - dot_r * 4, size - m - dot_r * 4,
               size - m - dot_r * 2, size - m - dot_r * 2], fill="#c8f56a")
    return im


def draw_og(w: int = 1200, h: int = 630) -> Image.Image:
    im = Image.new("RGB", (w, h), "#050505")
    d = ImageDraw.Draw(im)
    # ruler ticks along the top, like the chrome
    for x in range(0, w, 24):
        tick = 14 if (x // 24) % 5 == 0 else 7
        d.line([x, 0, x, tick], fill="#3a3a3a", width=1)
    mono_s = ImageFont.truetype(BOLD, 22)
    mono_xl = ImageFont.truetype(BOLD, 30)
    title = ImageFont.truetype(BOLD, 118)
    body = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 24)

    d.text((80, 60), "KAIROS.", font=ImageFont.truetype(BOLD, 40), fill="#ffffff")
    d.text((80, 190), "BUY OR WAIT?", font=title, fill="#ffffff")
    d.ellipse([640, 268, 676, 304], fill="#c8f56a")
    d.text((80, 356), "AI-POWERED FINANCIAL AFFORDABILITY AGENT", font=mono_xl, fill="#c8c8c8")
    d.text((80, 412),
           "250 requests decided · 90-day simulation per decision ·",
           font=body, fill="#8f8f8f")
    d.text((80, 448),
           "every row validated against the minimum-balance floor.",
           font=body, fill="#8f8f8f")
    d.text((80, 540), "DECISION INDEX — ABOUT — RESULTS — WORKFLOW — TEST BENCH",
           font=mono_s, fill="#5f5f5f")
    d.rectangle([80, 596, 1120, 598], fill="#242424")
    return im


# icons
icons = {}
for s in (16, 32, 48, 180, 192, 512):
    im = draw_k(s)
    icons[s] = im
    if s in (180, 192, 512):
        im.save(IMG / f"icon-{s}.png")
icons[16].save(IMG / "favicon-16.png")
icons[32].save(IMG / "favicon-32.png")
icons[48].save(IMG / "favicon-48.png")
icons[16].save(FRONTEND / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

# social preview
draw_og().save(IMG / "og-image.png")

print("wrote favicon.ico, favicon-16/32/48.png, icon-180/192/512.png, og-image.png")
