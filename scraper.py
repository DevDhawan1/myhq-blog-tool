import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urlparse
from collections import Counter
from datetime import datetime
import time

SITEMAP_URL = "https://myhqblog.in/sitemap-1.xml"
MYHQ_BASE   = "https://myhq.in"
BLOG_PREFIX = "/blog/"
CACHE_FILE  = "context_cache.json"
MAX_BLOGS   = 300  # raise if blog count grows beyond this

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


# ── Sitemap ───────────────────────────────────────────────────────────────────

def fetch_sitemap(url=SITEMAP_URL):
    """
    Fetches the sitemap XML from myhqblog.in, extracts paths,
    and returns full myhq.in/blog/... URLs.
    Handles both absolute and relative paths in the sitemap.
    """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml-xml")

    blog_urls = []
    for loc in soup.find_all("loc"):
        raw = loc.text.strip()
        path = urlparse(raw).path          # strip domain, keep path
        if path.startswith(BLOG_PREFIX):
            blog_urls.append(MYHQ_BASE + path)

    return blog_urls[:MAX_BLOGS]


# ── Single-page scraper ───────────────────────────────────────────────────────

def scrape_blog_post(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # ── Meta title ────────────────────────────────────────────────────────
        meta_title = ""
        if soup.title:
            raw_title = soup.title.get_text(strip=True)
            # strip trailing " | myHQ" or " - myHQ" site suffix
            meta_title = re.sub(
                r"\s*[\|\-–]\s*myHQ.*$", "", raw_title, flags=re.IGNORECASE
            ).strip()

        # ── Meta description ──────────────────────────────────────────────────
        meta_desc = ""
        tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if tag:
            meta_desc = tag.get("content", "").strip()

        # ── Meta keywords (not always present, but grab if exists) ────────────
        meta_keywords = ""
        tag = soup.find("meta", attrs={"name": re.compile(r"^keywords$", re.I)})
        if tag:
            meta_keywords = tag.get("content", "").strip()

        # ── H1 blog title ─────────────────────────────────────────────────────
        h1_title = ""
        for sel in ["h1.entry-title", "h1.post-title", ".entry-title", "h1"]:
            el = soup.select_one(sel)
            if el:
                h1_title = el.get_text(strip=True)
                break

        # ── Slug (last non-empty path segment) ────────────────────────────────
        parts = [p for p in urlparse(url).path.split("/") if p]
        slug = parts[-1] if parts else ""

        # ── Content area ──────────────────────────────────────────────────────
        content_el = None
        for sel in [".entry-content", ".post-content", "article .content",
                    "article", ".blog-content", "main"]:
            content_el = soup.select_one(sel)
            if content_el:
                break
        if not content_el:
            content_el = soup.find("body")

        content_text = content_el.get_text(separator=" ", strip=True) if content_el else ""

        # ── Outgoing links from content ───────────────────────────────────────
        links = []
        if content_el:
            for a in content_el.find_all("a", href=True):
                href = a["href"].strip()
                # normalise relative hrefs
                if href.startswith("/"):
                    href = MYHQ_BASE + href
                links.append((href, a.get_text(strip=True)))

        return {
            "url":           url,
            "slug":          slug,
            "h1_title":      h1_title,
            "meta_title":    meta_title,
            "meta_desc":     meta_desc,
            "meta_keywords": meta_keywords,
            "content_preview": content_text[:2500],
            "links":         links,
        }
    except Exception:
        return None


# ── Full context build ────────────────────────────────────────────────────────

def build_context(progress_callback=None):
    """
    Crawls all blog URLs, extracts content + SEO metadata,
    detects money pages, and caches everything.
    """
    urls = fetch_sitemap()
    total = len(urls)

    blogs       = []
    meta_examples = []        # real meta title/desc pairs for AI reference
    money_counter = Counter()
    money_anchors: dict = {}

    for i, url in enumerate(urls):
        if progress_callback:
            progress_callback(i / total, f"Scraping {i + 1}/{total}: {url}")

        data = scrape_blog_post(url)
        if not data:
            time.sleep(0.3)
            continue

        # Store blog entry
        blogs.append({
            "url":        data["url"],
            "slug":       data["slug"],
            "title":      data["h1_title"] or data["meta_title"],
            "meta_title": data["meta_title"],
            "meta_desc":  data["meta_desc"],
            "content_preview": data["content_preview"],
        })

        # Collect meta examples for AI reference (first 20 with real meta data)
        if len(meta_examples) < 20 and data["meta_title"] and data["meta_desc"]:
            meta_examples.append({
                "meta_title": data["meta_title"],
                "meta_desc":  data["meta_desc"],
                "keywords":   data["meta_keywords"],
            })

        # Money page detection:
        # Any myhq.in link that is NOT a /blog/ path = money / category page
        for link_url, anchor in data["links"]:
            parsed = urlparse(link_url)
            if "myhq.in" in parsed.netloc and not parsed.path.startswith(BLOG_PREFIX):
                if parsed.path and parsed.path != "/":
                    money_counter[link_url] += 1
                    if link_url not in money_anchors:
                        money_anchors[link_url] = []
                    if anchor and len(anchor) > 2 and anchor not in money_anchors[link_url]:
                        money_anchors[link_url].append(anchor)

        time.sleep(0.3)  # polite crawling

    top_money_pages = [
        {
            "url":        url,
            "link_count": count,
            "anchor_texts": money_anchors.get(url, [])[:5],
        }
        for url, count in money_counter.most_common(50)
    ]

    context = {
        "blogs":          blogs,
        "meta_examples":  meta_examples,
        "money_pages":    top_money_pages,
        "scraped_at":     datetime.now().isoformat(),
        "total_blogs":    len(blogs),
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    return context


# ── Cache helpers ─────────────────────────────────────────────────────────────

def load_context():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None
