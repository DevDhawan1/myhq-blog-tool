import io
import os
import random
import textwrap
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
UNSPLASH_BASE = "https://api.unsplash.com/photos/random"

# Font search paths — Windows first, then Linux/Mac (Streamlit Cloud)
_FONT_PATHS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Roboto-Bold.ttf"),
]


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_PATHS:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fetch_pollinations(prompt: str) -> bytes:
    """Download a 1280×720 background image from Pollinations.ai (free, no key)."""
    clean_prompt = (
        f"{prompt}. Photorealistic professional photography, "
        "sharp focus, high resolution, cinematic lighting, no text, no watermarks"
    )
    encoded = urllib.parse.quote(clean_prompt)
    seed = random.randint(1, 99999)
    url = (
        f"{POLLINATIONS_BASE}/{encoded}"
        f"?width=1280&height=720&model=flux-realism&nologo=true&seed={seed}"
    )
    resp = requests.get(url, timeout=90)
    if not resp.ok:
        raise RuntimeError(f"Pollinations returned {resp.status_code}")

    # Validate image bytes
    magic = resp.content[:4]
    if magic not in (b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'\x89PNG', b'RIFF'):
        raise RuntimeError("Pollinations returned non-image data")

    return resp.content


def _add_title_overlay(img_bytes: bytes, title: str) -> bytes:
    """Composite a dark gradient banner + blog title text onto the image."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size

    # ── Dark gradient from top (for text readability) ────────────────────────
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    banner_h = int(h * 0.46)
    for y in range(banner_h):
        alpha = int(200 * (1 - (y / banner_h) ** 0.55))
        draw_ov.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # ── Title text ────────────────────────────────────────────────────────────
    font_size = max(54, w // 17)
    font = _get_font(font_size)

    # Wrap to fit width (~0.55 * font_size per char is a safe estimate)
    max_chars = max(10, int(w / (font_size * 0.56)))
    lines = textwrap.wrap(title, width=max_chars)[:3]

    line_h = font_size + 16
    total_h = len(lines) * line_h
    y_start = max(20, int((banner_h - total_h) / 2))

    for i, line in enumerate(lines):
        y = y_start + i * line_h
        cx = w // 2
        # Drop shadow
        draw.text((cx + 3, y + 3), line, font=font, fill=(0, 0, 0, 200), anchor="mt")
        # White text
        draw.text((cx, y), line, font=font, fill=(255, 255, 255, 255), anchor="mt")

    # ── Return PNG bytes ───────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def generate_blog_image(image_prompt: str, blog_title: str) -> bytes:
    """
    Generate a blog feature image:
      1. Fetch a relevant background from Pollinations.ai (free, no key needed)
      2. Overlay the blog title as styled white text with a dark gradient banner
    Returns PNG bytes.
    """
    bg_bytes = _fetch_pollinations(image_prompt)
    return _add_title_overlay(bg_bytes, blog_title)


def get_unsplash_image(prompt: str, access_key: str) -> tuple[str, str]:
    """
    Fallback: fetch a relevant stock photo from Unsplash.
    Returns (image_url, credit_string).
    """
    query = prompt[:80].split(".")[0].strip()
    for search_query in [query, "office workspace", "coworking space"]:
        try:
            resp = requests.get(
                UNSPLASH_BASE,
                params={
                    "query": search_query,
                    "orientation": "landscape",
                    "client_id": access_key,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                img_url = data["urls"]["regular"]
                photographer = data["user"]["name"]
                link = data["links"]["html"] + "?utm_source=myHQ_blog_tool&utm_medium=referral"
                return img_url, f"Photo by [{photographer}]({link}) on Unsplash"
        except Exception:
            continue
    return "", ""
