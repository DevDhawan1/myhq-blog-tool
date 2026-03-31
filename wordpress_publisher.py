"""
WordPress REST API client for myHQ Blog Drafting Tool.
Handles media upload and post creation with SEO metadata.
"""
import requests
from requests.auth import HTTPBasicAuth


# ── Private helpers ───────────────────────────────────────────────────────────

def _normalise_site_url(site_url: str) -> str:
    url = site_url.strip().rstrip("/")
    if not url:
        raise ValueError("WordPress site URL is empty.")
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            f"WordPress site URL must start with http:// or https://. Got: {url!r}"
        )
    return url


def _check_wp_error(response: requests.Response, context: str) -> None:
    if response.ok:
        return

    status = response.status_code
    try:
        body = response.json()
        code    = body.get("code", "")
        message = body.get("message", response.text[:200])
    except Exception:
        code    = ""
        message = response.text[:200]

    if status == 401:
        raise RuntimeError(
            "Authentication failed (401). Check your WP username and Application Password. "
            "Generate one at WP Admin → Users → Profile → Application Passwords."
        )
    if status == 403:
        raise RuntimeError(
            f"Permission denied (403). Ensure the WP user has Editor or Administrator role. "
            f"WP says: {message}"
        )
    if status == 409 or "exist" in code.lower() or "duplicate" in code.lower():
        raise RuntimeError(
            "Slug conflict: a post with this slug already exists on WordPress. "
            "Either delete the existing draft in WP Admin, or change the URL slug before publishing."
        )
    if "rest_cannot_create" in code:
        raise RuntimeError(
            f"REST API create permission denied ({code}). "
            "Check that the WP Application Password has write access."
        )
    raise RuntimeError(f"{context} failed ({status}): [{code}] {message}")


# ── Public API ────────────────────────────────────────────────────────────────

def upload_media(
    site_url: str,
    username: str,
    app_password: str,
    image_bytes: bytes,
    filename: str = "feature-image.png",
    alt_text: str = "",
) -> int:
    """
    Upload PNG bytes to the WP media library via POST /wp-json/wp/v2/media.

    Returns the WP attachment post ID (int).
    Raises ValueError if image_bytes is empty.
    Raises RuntimeError on auth failure or non-2xx response.
    """
    if not image_bytes:
        raise ValueError("image_bytes is empty — no image to upload.")

    base = _normalise_site_url(site_url)
    auth = HTTPBasicAuth(username, app_password.replace(" ", ""))
    media_url = f"{base}/wp-json/wp/v2/media"

    resp = requests.post(
        media_url,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "image/png",
        },
        data=image_bytes,
        auth=auth,
        timeout=60,
    )
    _check_wp_error(resp, "Media upload")

    data = resp.json()
    media_id = data.get("id")
    if not media_id:
        raise RuntimeError("Media upload succeeded but WP returned no media ID.")

    # Set alt text and title via PATCH
    if alt_text:
        requests.post(
            f"{media_url}/{media_id}",
            json={"alt_text": alt_text, "title": alt_text},
            auth=auth,
            timeout=15,
        )

    return int(media_id)


def create_post(
    site_url: str,
    username: str,
    app_password: str,
    title: str,
    content: str,
    slug: str,
    meta_title: str,
    meta_description: str,
    focus_keyword: str,
    status: str = "draft",
    featured_media_id: int = 0,
) -> dict:
    """
    Create a WP post via POST /wp-json/wp/v2/posts.

    Parameters
    ----------
    status            : "draft" or "publish"
    featured_media_id : WP attachment ID from upload_media(); 0 = no featured image

    Returns
    -------
    {
        "post_id":  int,
        "post_url": str,   # public-facing URL
        "edit_url": str,   # WP Admin edit link
        "status":   str,   # confirmed status from WP
    }

    Raises RuntimeError on auth failure, slug conflict, or non-2xx response.
    """
    base = _normalise_site_url(site_url)
    auth = HTTPBasicAuth(username, app_password.replace(" ", ""))

    payload = {
        "title":   title,
        "content": content,
        "slug":    slug,
        "status":  status,
        "meta": {
            # Yoast SEO fields
            "_yoast_wpseo_title":      meta_title,
            "_yoast_wpseo_metadesc":   meta_description,
            "_yoast_wpseo_focuskw":    focus_keyword,
            # RankMath fields
            "rank_math_title":            meta_title,
            "rank_math_description":      meta_description,
            "rank_math_focus_keyword":    focus_keyword,
        },
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    resp = requests.post(
        f"{base}/wp-json/wp/v2/posts",
        json=payload,
        auth=auth,
        timeout=30,
    )
    _check_wp_error(resp, "Post creation")

    data    = resp.json()
    post_id = data["id"]

    return {
        "post_id":  post_id,
        "post_url": data.get("link", ""),
        "edit_url": f"{base}/wp-admin/post.php?post={post_id}&action=edit",
        "status":   data.get("status", status),
    }
