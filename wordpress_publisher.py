"""
WordPress REST API client for myHQ Blog Drafting Tool.
Handles media upload and post creation with SEO metadata.
"""
import json
import re
import requests
from requests.auth import HTTPBasicAuth


# ── Gutenberg block converter ─────────────────────────────────────────────────

def _html_to_gutenberg(html: str) -> str:
    """
    Convert raw HTML to WordPress Gutenberg block format so the post is
    stored as discrete blocks rather than a single classic/HTML block.

    Handles: h2, h3, p, ul/li, table, div, script.
    """
    # Strip a single outer wrapper <div> that the AI sometimes adds around the
    # entire content — if left in, the div regex consumes everything as one HTML block.
    html = html.strip()
    outer_div = re.match(r'^<div[^>]*>(.*)</div>\s*$', html, re.DOTALL)
    if outer_div:
        # Only unwrap if the outermost div contains block-level tags (h2/h3/p)
        inner = outer_div.group(1).strip()
        if re.search(r'<(?:h[23]|p)\b', inner, re.IGNORECASE):
            html = inner

    blocks = []

    pattern = re.compile(
        r'(<h2[^>]*>.*?</h2>'
        r'|<h3[^>]*>.*?</h3>'
        r'|<p[^>]*>.*?</p>'
        r'|<ul[^>]*>.*?</ul>'
        r'|<ol[^>]*>.*?</ol>'
        r'|<table[^>]*>.*?</table>'
        r'|<div[^>]*>.*?</div>'
        r'|<script[^>]*>.*?</script>)',
        re.DOTALL,
    )

    # re.split() with a capturing group includes the matches inline —
    # no need for a separate findall(); doing both causes every block to appear twice.
    for part in pattern.split(html):
        part = part.strip()
        if not part:
            continue

        if re.match(r'<h2', part):
            blocks.append(f'<!-- wp:heading {{"level":2}} -->\n{part}\n<!-- /wp:heading -->')

        elif re.match(r'<h3', part):
            blocks.append(f'<!-- wp:heading {{"level":3}} -->\n{part}\n<!-- /wp:heading -->')

        elif re.match(r'<p', part):
            blocks.append(f'<!-- wp:paragraph -->\n{part}\n<!-- /wp:paragraph -->')

        elif re.match(r'<ul', part):
            inner = re.sub(
                r'<li([^>]*)>(.*?)</li>',
                r'<!-- wp:list-item --><li\1>\2</li><!-- /wp:list-item -->',
                part, flags=re.DOTALL,
            )
            blocks.append(f'<!-- wp:list -->\n{inner}\n<!-- /wp:list -->')

        elif re.match(r'<ol', part):
            inner = re.sub(
                r'<li([^>]*)>(.*?)</li>',
                r'<!-- wp:list-item --><li\1>\2</li><!-- /wp:list-item -->',
                part, flags=re.DOTALL,
            )
            blocks.append(f'<!-- wp:list {{"ordered":true}} -->\n{inner}\n<!-- /wp:list -->')

        elif re.match(r'<table', part):
            blocks.append(
                f'<!-- wp:table -->\n'
                f'<figure class="wp-block-table">{part}</figure>\n'
                f'<!-- /wp:table -->'
            )

        else:
            # div, script, or anything else → raw HTML block
            blocks.append(f'<!-- wp:html -->\n{part}\n<!-- /wp:html -->')

    return '\n\n'.join(blocks)


# ── RankMath FAQ block converter ─────────────────────────────────────────────

def _convert_faq_to_rankmath(gutenberg: str) -> str:
    """
    Finds the FAQ section inside already-converted Gutenberg block content and
    replaces the individual h3/paragraph block pairs with a single
    <!-- wp:rank-math/faq-block --> so RankMath renders them as structured FAQs.
    """
    # Locate the FAQ H2 heading block
    faq_h2 = re.compile(
        r'<!-- wp:heading \{"level":2\} -->\s*<h2[^>]*>\s*Frequently Asked Questions\s*</h2>\s*<!-- /wp:heading -->',
        re.IGNORECASE,
    )
    m = faq_h2.search(gutenberg)
    if not m:
        return gutenberg

    after_h2 = gutenberg[m.end():]

    # Match h3 + answer block pairs; answer can be a <p> paragraph OR a <ul>/<ol> list
    pair = re.compile(
        r'\s*<!-- wp:heading \{"level":3\} -->\s*<h3[^>]*>(.*?)</h3>\s*<!-- /wp:heading -->'
        r'\s*(?:'
        r'<!-- wp:paragraph -->\s*(<p[^>]*>.*?</p>)\s*<!-- /wp:paragraph -->'
        r'|<!-- wp:list(?:[^-]|-(?!-))*?-->\s*(<ul[^>]*>.*?</ul>)\s*<!-- /wp:list -->'
        r')',
        re.DOTALL | re.IGNORECASE,
    )

    questions, html_items, consumed = [], [], 0
    for pm in pair.finditer(after_h2):
        # Stop if a non-FAQ h2 appears between the previous match and this one
        if '<!-- wp:heading {"level":2}' in after_h2[consumed:pm.start()]:
            break
        q = re.sub(r'<[^>]+>', '', pm.group(1)).strip()
        # group(2) = paragraph answer, group(3) = list answer
        if pm.group(2):
            a_html = pm.group(2).strip()        # full <p>...</p>
        else:
            # Flatten list items into a paragraph for RankMath schema
            items = re.findall(r'<li[^>]*>(.*?)</li>', pm.group(3) or '', re.DOTALL)
            a_html = '<p>' + ' '.join(re.sub(r'<[^>]+>', '', i).strip() for i in items) + '</p>'
        fid = f"faq-question-{len(questions) + 1}"
        questions.append({"id": fid, "title": q, "content": a_html, "visible": True})
        html_items.append(
            f'<div class="rank-math-faq-item">'
            f'<h3 class="rank-math-question">{q}</h3>'
            f'<div class="rank-math-answer">{a_html}</div>'
            f'</div>'
        )
        consumed = pm.end()

    if not questions:
        return gutenberg

    attrs = json.dumps({"questions": questions, "className": ""}, separators=(',', ':'))
    faq_block = (
        '<!-- wp:heading {"level":2} -->\n'
        '<h2 class="wp-block-heading">Frequently Asked Questions</h2>\n'
        '<!-- /wp:heading -->\n\n'
        f'<!-- wp:rank-math/faq-block {attrs} -->\n'
        '<div class="wp-block-rank-math-faq-block">\n'
        + '\n'.join(html_items)
        + '\n</div>\n'
        '<!-- /wp:rank-math/faq-block -->'
    )

    return gutenberg[: m.start()] + faq_block + after_h2[consumed:]


# ── Private helpers ───────────────────────────────────────────────────────────

def _normalise_site_url(site_url: str) -> str:
    url = site_url.strip().rstrip("/")
    if not url:
        raise ValueError("WordPress site URL is empty.")
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            f"WordPress site URL must start with http:// or https://. Got: {url!r}"
        )
    # Strip common suffixes users accidentally paste
    for suffix in ("/wp-admin", "/wp-login.php", "/wp-json"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


def _discover_api_base(site_url: str, auth: HTTPBasicAuth) -> str:
    """
    Resolve the true WP REST API base URL by following redirects on a GET
    to /wp-json/. Returns the base site URL after redirects (no trailing slash,
    no /wp-json suffix), so callers can append /wp-json/wp/v2/... themselves.

    Raises RuntimeError with a human-readable message if the REST API is
    unreachable or returns non-JSON (e.g. pretty permalinks disabled).
    """
    discovery_url = f"{site_url}/wp-json/"
    try:
        resp = requests.get(discovery_url, auth=auth, timeout=15, allow_redirects=True)
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot connect to WordPress at {site_url}: {e}")

    # If we were redirected, derive the new base from the final URL
    final_url = resp.url  # e.g. https://www.myhqblog.in/wp-json/
    resolved_base = final_url.rstrip("/")
    if resolved_base.endswith("/wp-json"):
        resolved_base = resolved_base[: -len("/wp-json")]

    if not resp.ok or "application/json" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError(
            f"WordPress REST API not found at {discovery_url}. "
            "Possible causes:\n"
            "  • Permalink structure is set to 'Plain' — change it to 'Post name' "
            "in WP Admin → Settings → Permalinks.\n"
            f"  • The site URL you entered ({site_url}) redirects to a different domain. "
            f"Try using {resolved_base} instead."
        )

    return resolved_base


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


def _resolve_tag_ids(base: str, auth: HTTPBasicAuth, tag_names: list[str]) -> list[int]:
    """Look up tag IDs by name; create any that don't exist. Returns list of IDs."""
    ids = []
    tag_url = f"{base}/wp-json/wp/v2/tags"
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        try:
            resp = requests.get(tag_url, params={"search": name, "per_page": 5}, auth=auth, timeout=10)
            if resp.ok:
                matches = [t for t in resp.json() if t["name"].lower() == name.lower()]
                if matches:
                    ids.append(matches[0]["id"])
                    continue
            resp = requests.post(tag_url, json={"name": name}, auth=auth, timeout=10)
            if resp.ok:
                ids.append(resp.json()["id"])
        except Exception:
            pass
    return ids


def _set_rankmath_meta(base: str, auth: HTTPBasicAuth, post_id: int,
                       meta_title: str, meta_description: str,
                       focus_keyword: str, canonical_url: str = "") -> str | None:
    """
    Call the dedicated Rank Math REST endpoint to write SEO meta.
    Returns a warning string on failure, None on success.
    """
    meta = {
        "rank_math_title":         meta_title,
        "rank_math_description":   meta_description,
        "rank_math_focus_keyword": focus_keyword,
    }
    if canonical_url:
        meta["rank_math_canonical_url"] = canonical_url

    try:
        resp = requests.post(
            f"{base}/wp-json/rankmath/v1/updateMeta",
            json={"objectType": "post", "objectID": post_id, "meta": meta},
            auth=auth,
            timeout=15,
        )
        if resp.ok:
            return None
        return f"Rank Math API returned {resp.status_code}. SEO meta may need manual entry."
    except Exception as e:
        return f"Rank Math API error: {e}"


def _resolve_category_ids(base: str, auth: HTTPBasicAuth, category_names: list[str]) -> list[int]:
    """
    Given a list of category name strings, return matching WP category IDs.
    Creates any category that doesn't already exist.
    Silently skips on any error so publishing always continues.
    """
    ids = []
    cat_url = f"{base}/wp-json/wp/v2/categories"
    for name in category_names:
        name = name.strip()
        if not name:
            continue
        try:
            # Search for existing category
            resp = requests.get(
                cat_url,
                params={"search": name, "per_page": 5},
                auth=auth,
                timeout=10,
            )
            if resp.ok:
                matches = [c for c in resp.json() if c["name"].lower() == name.lower()]
                if matches:
                    ids.append(matches[0]["id"])
                    continue

            # Not found — create it
            resp = requests.post(
                cat_url,
                json={"name": name},
                auth=auth,
                timeout=10,
            )
            if resp.ok:
                ids.append(resp.json()["id"])
        except Exception:
            pass  # Non-fatal — post will still be created without this category

    return ids


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
    base = _discover_api_base(base, auth)
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

    source_url = data.get("source_url", "")
    return {"id": int(media_id), "url": source_url}


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
    featured_media_url: str = "",
    schema_markup: str = "",
    author_html: str = "",
    category_names: list[str] | None = None,
    tag_names: list[str] | None = None,
    canonical_url: str = "",
) -> dict:
    """
    Create a WP post via POST /wp-json/wp/v2/posts.

    Parameters
    ----------
    status            : "draft" or "publish"
    featured_media_id : WP attachment ID from upload_media(); 0 = no featured image
    schema_markup     : JSON-LD string (without <script> tags) — prepended to content
    author_html       : HTML string for author bio block — appended to content
    category_names    : list of WP category name strings; looked up / created automatically

    Returns
    -------
    {
        "post_id":  int,
        "post_url": str,
        "edit_url": str,
        "status":   str,
    }
    """
    base = _normalise_site_url(site_url)
    auth = HTTPBasicAuth(username, app_password.replace(" ", ""))
    base = _discover_api_base(base, auth)

    # ── Normalise internal blog links to the publishing domain ───────────────
    # The generator uses myhq.in/blog/ URLs (from the scraper context), but the
    # WordPress site lives on myhqblog.in. RankMath only counts same-domain links
    # as internal, so we rewrite them here before publishing.
    content = content.replace("https://myhq.in/blog/", "https://myhqblog.in/blog/")

    # ── Convert HTML → Gutenberg blocks → RankMath FAQ block ─────────────────
    block_content = _convert_faq_to_rankmath(_html_to_gutenberg(content))

    # ── Inject feature image block before first H2 (after intro paragraphs) ─────
    if featured_media_id:
        src_attr = f' src="{featured_media_url}"' if featured_media_url else ""
        img_block = (
            f'<!-- wp:image {{"id":{featured_media_id},"sizeSlug":"large","linkDestination":"none"}} -->\n'
            f'<figure class="wp-block-image size-large">'
            f'<img{src_attr} alt="{title}" class="wp-image-{featured_media_id}"/>'
            f'</figure>\n'
            f'<!-- /wp:image -->'
        )
        # Insert just before the first H2 heading block
        h2_marker = '<!-- wp:heading {"level":2} -->'
        pos = block_content.find(h2_marker)
        if pos != -1:
            block_content = (
                block_content[:pos]
                + img_block + "\n\n"
                + block_content[pos:]
            )
        else:
            # Fallback: after first paragraph block
            for marker in ("<!-- /wp:paragraph -->", "<!-- /wp:heading -->", "<!-- /wp:html -->"):
                pos = block_content.find(marker)
                if pos != -1:
                    insert_pos = pos + len(marker)
                    block_content = (
                        block_content[:insert_pos]
                        + "\n\n" + img_block + "\n\n"
                        + block_content[insert_pos:]
                    )
                    break

    # ── Assemble full content ─────────────────────────────────────────────────
    full_content = block_content
    if schema_markup:
        try:
            json.loads(schema_markup)
            schema_block = (
                f'<!-- wp:html -->\n'
                f'<script type="application/ld+json">{schema_markup}</script>\n'
                f'<!-- /wp:html -->'
            )
            full_content = schema_block + "\n\n" + full_content
        except Exception:
            pass

    if author_html:
        full_content = full_content + "\n\n<!-- wp:html -->\n" + author_html + "\n<!-- /wp:html -->"

    # ── Resolve category and tag IDs ─────────────────────────────────────────
    cat_ids = _resolve_category_ids(base, auth, category_names or [])
    tag_ids = _resolve_tag_ids(base, auth, tag_names or [])

    # ── Build payload ─────────────────────────────────────────────────────────
    payload = {
        "title":   title,
        "content": full_content,
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
    if cat_ids:
        payload["categories"] = cat_ids
    if tag_ids:
        payload["tags"] = tag_ids

    resp = requests.post(
        f"{base}/wp-json/wp/v2/posts",
        json=payload,
        auth=auth,
        timeout=30,
    )
    _check_wp_error(resp, "Post creation")

    data    = resp.json()
    post_id = data["id"]

    # ── Step 1: dedicated Rank Math API ──────────────────────────────────────
    meta_warning = _set_rankmath_meta(
        base, auth, post_id, meta_title, meta_description, focus_keyword, canonical_url
    )

    # ── Step 2: fallback PATCH via WP REST meta fields ────────────────────────
    seo_meta = {
        "rank_math_title":         meta_title,
        "rank_math_description":   meta_description,
        "rank_math_focus_keyword": focus_keyword,
        "_yoast_wpseo_title":      meta_title,
        "_yoast_wpseo_metadesc":   meta_description,
        "_yoast_wpseo_focuskw":    focus_keyword,
    }
    try:
        meta_resp = requests.post(
            f"{base}/wp-json/wp/v2/posts/{post_id}",
            json={"meta": seo_meta},
            auth=auth,
            timeout=15,
        )
        if meta_resp.ok:
            written = meta_resp.json().get("meta", {})
            if meta_warning and written.get("rank_math_description", "") == meta_description:
                meta_warning = None   # Rank Math API failed but PATCH worked — clear warning
        elif meta_warning:
            meta_warning += (
                "\n\nWP meta PATCH also failed. To fix, add this to functions.php:\n"
                "add_action('init', function() {\n"
                "    foreach(['rank_math_title','rank_math_description','rank_math_focus_keyword'] as $k)\n"
                "        register_post_meta('post', $k, ['show_in_rest'=>true,'single'=>true,'type'=>'string',\n"
                "            'auth_callback'=>fn()=>current_user_can('edit_posts')]);\n"
                "});"
            )
    except Exception:
        pass

    return {
        "post_id":      post_id,
        "post_url":     data.get("link", ""),
        "edit_url":     f"{base}/wp-admin/post.php?post={post_id}&action=edit",
        "status":       data.get("status", status),
        "meta_warning": meta_warning,
    }
