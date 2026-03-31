import os
import random
import urllib.parse

import requests

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
UNSPLASH_BASE = "https://api.unsplash.com/photos/random"
FREE_IMAGE_API_URL = "https://free-image-generator-api.devanshdhawan8943.workers.dev"


def _fetch_custom_api(prompt: str, api_url: str, api_key: str) -> bytes:
    """Fetch image bytes from the self-hosted free-image-generator-api (Cloudflare Worker)."""
    resp = requests.post(
        api_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"prompt": prompt},
        timeout=90,
    )
    if not resp.ok:
        raise RuntimeError(f"Custom image API returned {resp.status_code}: {resp.text[:200]}")

    content = resp.content
    # Accept any JPEG (FF D8 start marker) or PNG/WebP
    if content[:2] != b'\xff\xd8' and content[:4] not in (b'\x89PNG', b'RIFF'):
        raise RuntimeError(
            f"Custom image API returned non-image data "
            f"(first bytes: {content[:8].hex()})"
        )

    return content


def _fetch_pollinations(prompt: str) -> bytes:
    """Fallback: download an image from Pollinations.ai (free, no key)."""
    encoded = urllib.parse.quote(prompt)
    seed = random.randint(1, 99999)
    url = (
        f"{POLLINATIONS_BASE}/{encoded}"
        f"?width=1280&height=720&model=flux-realism&nologo=true&seed={seed}"
    )
    resp = requests.get(url, timeout=90)
    if not resp.ok:
        raise RuntimeError(f"Pollinations returned {resp.status_code}")

    magic = resp.content[:4]
    if magic not in (b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'\x89PNG', b'RIFF'):
        raise RuntimeError("Pollinations returned non-image data")

    return resp.content


def generate_blog_image(
    blog_title: str,
    api_url: str = "",
    api_key: str = "",
) -> bytes:
    """
    Generate a blog feature image using the blog title as the prompt.

    Priority:
      1. Self-hosted Cloudflare Worker (free-image-generator-api) — if api_key is set
      2. Pollinations.ai (free, no key) — fallback

    Returns raw image bytes (JPEG or PNG). No text overlay is added.
    """
    api_url = api_url or os.environ.get("FREE_IMAGE_API_URL", FREE_IMAGE_API_URL)
    api_key = api_key or os.environ.get("FREE_IMAGE_API_KEY", "")

    if api_key:
        try:
            return _fetch_custom_api(blog_title, api_url, api_key)
        except Exception as e:
            print(f"[image_generator] Custom API failed ({e}), falling back to Pollinations")

    return _fetch_pollinations(blog_title)


def get_unsplash_image(prompt: str, access_key: str) -> tuple[str, str]:
    """
    Last-resort fallback: fetch a relevant stock photo from Unsplash.
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
