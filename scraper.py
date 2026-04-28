import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
from datetime import datetime

BLOG_BASE  = "https://myhqblog.in"
MYHQ_BASE  = "https://myhq.in"
CACHE_FILE = "context_cache.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Category IDs on myhqblog.in
CATEGORY_IDS = {
    "Virtual Office": 207363,
    "Office Space":   207371,
    "Meeting Room":   207411,
    "Business Hubs":  207392,
}

# Static money pages by product line — covers VO, coworking, managed office, bare shell
MONEY_PAGES = [
    # Virtual Office
    {"url": "https://myhq.in/virtual-office",                   "anchor_texts": ["virtual office", "virtual office services"],            "link_count": 50},
    {"url": "https://myhq.in/virtual-office/bangalore",         "anchor_texts": ["virtual office in Bangalore", "Bangalore virtual office"], "link_count": 40},
    {"url": "https://myhq.in/virtual-office/mumbai",            "anchor_texts": ["virtual office in Mumbai"],                              "link_count": 35},
    {"url": "https://myhq.in/virtual-office/delhi",             "anchor_texts": ["virtual office in Delhi"],                               "link_count": 30},
    {"url": "https://myhq.in/virtual-office/hyderabad",         "anchor_texts": ["virtual office in Hyderabad"],                           "link_count": 25},
    {"url": "https://myhq.in/virtual-office/pune",              "anchor_texts": ["virtual office in Pune"],                                "link_count": 20},
    {"url": "https://myhq.in/virtual-office/chennai",           "anchor_texts": ["virtual office in Chennai"],                             "link_count": 18},
    {"url": "https://myhq.in/virtual-office/gurgaon",           "anchor_texts": ["virtual office in Gurgaon"],                             "link_count": 15},
    {"url": "https://myhq.in/virtual-office/noida",             "anchor_texts": ["virtual office in Noida"],                               "link_count": 12},
    # Coworking
    {"url": "https://myhq.in/coworking-spaces",                 "anchor_texts": ["coworking spaces", "coworking space"],                   "link_count": 45},
    {"url": "https://myhq.in/coworking-spaces/bangalore",       "anchor_texts": ["coworking spaces in Bangalore"],                         "link_count": 38},
    {"url": "https://myhq.in/coworking-spaces/mumbai",          "anchor_texts": ["coworking spaces in Mumbai"],                            "link_count": 32},
    {"url": "https://myhq.in/coworking-spaces/delhi",           "anchor_texts": ["coworking spaces in Delhi"],                             "link_count": 28},
    {"url": "https://myhq.in/coworking-spaces/hyderabad",       "anchor_texts": ["coworking spaces in Hyderabad"],                         "link_count": 22},
    {"url": "https://myhq.in/coworking-spaces/pune",            "anchor_texts": ["coworking spaces in Pune"],                              "link_count": 18},
    {"url": "https://myhq.in/coworking-spaces/gurgaon",         "anchor_texts": ["coworking spaces in Gurgaon"],                           "link_count": 15},
    {"url": "https://myhq.in/coworking-spaces/chennai",         "anchor_texts": ["coworking spaces in Chennai"],                           "link_count": 14},
    # Managed Office
    {"url": "https://myhq.in/managed-office-space",             "anchor_texts": ["managed office space", "managed office"],                "link_count": 30},
    {"url": "https://myhq.in/managed-office-space/bangalore",   "anchor_texts": ["managed office space in Bangalore"],                     "link_count": 20},
    {"url": "https://myhq.in/managed-office-space/mumbai",      "anchor_texts": ["managed office in Mumbai"],                              "link_count": 15},
    {"url": "https://myhq.in/managed-office-space/hyderabad",   "anchor_texts": ["managed office in Hyderabad"],                           "link_count": 12},
    # Bare Shell / Commercial Leasing
    {"url": "https://myhq.in/commercial-real-estate",           "anchor_texts": ["commercial real estate", "commercial office space"],     "link_count": 20},
    {"url": "https://myhq.in/commercial-real-estate/bangalore", "anchor_texts": ["commercial office space in Bangalore"],                  "link_count": 14},
]


def _clean_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


# ── WP REST API fetchers ──────────────────────────────────────────────────────

def _fetch_posts_page(site_url: str, page: int, category_id: int | None = None) -> list[dict]:
    params = {
        "per_page": 100,
        "page": page,
        "_fields": "id,slug,title,link,excerpt,categories",
        "status": "publish",
    }
    if category_id:
        params["categories"] = category_id
    resp = requests.get(
        f"{site_url}/wp-json/wp/v2/posts",
        params=params,
        headers=HEADERS,
        timeout=15,
    )
    if resp.status_code in (400, 404):
        return []
    resp.raise_for_status()
    return resp.json() or []


def fetch_blogs_via_api(site_url: str = BLOG_BASE, progress_callback=None) -> list[dict]:
    """Fetch all published posts via WP REST API (paginated)."""
    posts, page = [], 1
    while True:
        if progress_callback:
            progress_callback(min(page * 0.08, 0.7), f"Fetching posts page {page}…")
        batch = _fetch_posts_page(site_url, page)
        if not batch:
            break
        posts.extend(batch)
        page += 1
        if len(batch) < 100:
            break
    return posts


def fetch_internal_links_for_category(category: str, site_url: str = BLOG_BASE) -> list[dict]:
    """Fetch recent posts from a WP category for live internal link data at generation time."""
    cat_id = CATEGORY_IDS.get(category)
    try:
        batch = _fetch_posts_page(site_url, 1, category_id=cat_id)
        return [
            {
                "url":   p.get("link", "").replace(BLOG_BASE, MYHQ_BASE).replace("www.myhqblog.in", "myhq.in"),
                "title": _clean_html(p.get("title", {}).get("rendered", "")),
                "slug":  p.get("slug", ""),
            }
            for p in batch
            if p.get("slug") and p.get("title")
        ]
    except Exception:
        return []


# ── Tone sample scraper (myhq.in/blog/ is accessible) ────────────────────────

def _scrape_tone_sample(url: str) -> str | None:
    """Fetch a blog post from myhq.in and return its opening content (~600 chars)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        content_el = (
            soup.select_one(".entry-content")
            or soup.select_one(".post-content")
            or soup.select_one("article")
            or soup.find("main")
        )
        if not content_el:
            return None
        text = re.sub(r"\s+", " ", content_el.get_text(separator=" ", strip=True))
        return text[:600]
    except Exception:
        return None


def _get_tone_samples(posts: list[dict], count: int = 6) -> list[dict]:
    """
    Enrich the first `count` posts with a full content preview by scraping
    the myhq.in/blog/ URL (accessible even when myhqblog.in is blocked).
    """
    enriched = []
    for post in posts[:count * 2]:                    # try extras in case some fail
        if len(enriched) >= count:
            break
        myhq_url = post.get("url", "")
        if not myhq_url:
            continue
        sample = _scrape_tone_sample(myhq_url)
        if sample:
            enriched.append({**post, "content_preview": sample})
        time.sleep(0.3)
    return enriched


# ── Full context build ────────────────────────────────────────────────────────

def build_context(progress_callback=None):
    """
    Fetch all blog posts via WP REST API, enrich 6 posts with tone samples
    from myhq.in/blog/, and cache everything to context_cache.json.
    """
    if progress_callback:
        progress_callback(0.0, "Connecting to WordPress REST API…")

    raw_posts = fetch_blogs_via_api(progress_callback=progress_callback)

    if progress_callback:
        progress_callback(0.75, f"Fetched {len(raw_posts)} posts. Scraping tone samples…")

    blogs = []
    for p in raw_posts:
        title   = _clean_html(p.get("title", {}).get("rendered", ""))
        excerpt = _clean_html(p.get("excerpt", {}).get("rendered", ""))
        slug    = p.get("slug", "")
        link    = p.get("link", "")
        canonical = link.replace(BLOG_BASE, MYHQ_BASE).replace("www.myhqblog.in", "myhq.in")

        if title and slug:
            blogs.append({
                "url":             canonical,
                "slug":            slug,
                "title":           title,
                "meta_title":      title,
                "meta_desc":       excerpt[:160],
                "content_preview": excerpt,   # overwritten below for first 6
            })

    # Enrich first 6 with real content previews for tone matching
    tone_enriched = _get_tone_samples(blogs, count=6)
    tone_map = {b["url"]: b for b in tone_enriched}
    blogs = [tone_map.get(b["url"], b) for b in blogs]

    if progress_callback:
        progress_callback(0.95, "Building context cache…")

    meta_examples = [
        {"meta_title": b["meta_title"], "meta_desc": b["meta_desc"], "keywords": ""}
        for b in blogs[:20]
        if b.get("meta_title") and b.get("meta_desc")
    ]

    context = {
        "blogs":        blogs,
        "meta_examples": meta_examples,
        "money_pages":  MONEY_PAGES,
        "scraped_at":   datetime.now().isoformat(),
        "total_blogs":  len(blogs),
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    if progress_callback:
        progress_callback(1.0, f"Done! Indexed {len(blogs)} posts.")

    return context


# ── Cache helpers ─────────────────────────────────────────────────────────────

def load_context():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None
