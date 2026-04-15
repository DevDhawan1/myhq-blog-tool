# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Streamlit app
python -m streamlit run app.py

# Windows shortcut
run.bat
```

## Environment Variables

Create a `.env` file in the project root (loaded manually by `app.py` via line-by-line parsing — no `python-dotenv` at runtime):

```
GEMINI_API_KEY=your_key_here                 # required if using Gemini provider
GROQ_API_KEY=your_key_here                   # required if using Groq provider (free tier: 14,400 req/day)
FREE_IMAGE_API_KEY=your_bearer_token         # bearer token for the Cloudflare Worker image API
UNSPLASH_ACCESS_KEY=your_key_here            # optional, last-resort image fallback
WP_SITE_URL=https://myhqblog.in             # optional, WordPress publishing
WP_USERNAME=your_wp_username                 # optional, WordPress publishing
WP_APP_PASSWORD=xxxx xxxx xxxx              # optional, WP Application Password
```

All keys can also be entered at runtime via the Streamlit sidebar.

## Architecture

The app is a **Streamlit single-page tool** for generating SEO-optimised blog drafts for myHQ. Data flows as follows:

1. **`scraper.py`** — crawls `myhqblog.in` via `sitemap-1.xml`, scrapes each blog post for content, meta tags, and outgoing links. Any `myhq.in` link that isn't a `/blog/` path is classified as a **money page**. Results are persisted to `context_cache.json`. Blog URLs are normalised from `myhqblog.in` → `myhq.in` before storage.

2. **`generator.py`** — supports two LLM providers (selectable in sidebar):
   - **Gemini** (`setup_gemini` / `generate_blog`) — uses `response_mime_type="application/json"` with a strict `response_schema` to enforce structured output. Selectable model (default `gemini-2.0-flash`). Auto-retries on 429 rate limits with backoff; detects daily quota exhaustion and raises a clear error.
   - **Groq** (`setup_groq` / `generate_blog_groq`) — uses `llama-3.3-70b-versatile` with `response_format={"type": "json_object"}`. Prompt is sent in `compact=True` mode: fewer tone samples, smaller link pools, and capped word count (max 900) to stay within Groq's 12k TPM free-tier limit.
   - Both providers share `_build_prompt()` and `_fix_result()`. Post-generation, the result is validated: focus keyword is force-injected into the meta description if missing, and the URL slug is overwritten to contain the focus keyword words.

3. **`image_generator.py`** — generates a blog feature image via `generate_blog_image(blog_title, api_key)`. Priority: (1) `FREE_IMAGE_API_URL` Cloudflare Worker — POST `{"prompt": "..."}` with `Authorization: Bearer <key>`, returns raw JPEG/PNG; (2) Pollinations.ai (free, no key) as fallback. Returns raw image bytes with no text overlay. Unsplash (`get_unsplash_image`) is a last-resort fallback triggered only from `app.py` if both generate paths throw.

4. **`docx_exporter.py`** — converts the generated HTML blog content into a `.docx` via a regex-based HTML parser (`_parse_html_to_doc`). Handles `h2`, `h3`, `p`, `ul/li`, `a`, and `table` tags. Includes the feature image and an SEO metadata table.

5. **`wordpress_publisher.py`** — publishes to WordPress via the REST API (`/wp-json/wp/v2/`). Key pipeline:
   - `_html_to_gutenberg()` converts raw HTML to Gutenberg block markup (headings, paragraphs, lists, tables, raw HTML blocks).
   - `_convert_faq_to_rankmath()` rewrites FAQ h3/answer pairs into a `<!-- wp:rank-math/faq-block -->` so RankMath generates FAQ structured data.
   - `_discover_api_base()` follows redirects on `/wp-json/` to resolve the real API base URL (handles domain mismatches like `myhqblog.in` → `www.myhqblog.in`).
   - At publish time, internal blog URLs are rewritten from `myhq.in/blog/` → `myhqblog.in/blog/` so RankMath counts them as internal links.
   - `upload_media` POSTs the feature image and returns `{id, url}`; `create_post` creates the post with both Yoast SEO and RankMath meta fields. A follow-up PATCH writes SEO meta separately (needed because WP doesn't always persist custom meta on initial create). WP Application Passwords have spaces stripped internally.

6. **`app.py`** — orchestrates the UI. Context is loaded once at startup from cache. Blog generation, image generation, and DOCX build are triggered by user actions. Session state persists the generated result and image bytes across Streamlit rerenders. DOCX is auto-saved to `~/Downloads/` on first render after generation.

## Key Behavioural Details

- `context_cache.json` is written relative to the script's CWD — always run the app from the project directory.
- The scraper politely sleeps 0.3s between requests and caps at `MAX_BLOGS = 1000`.
- Money pages are the top 50 most-linked `myhq.in` non-blog URLs, sorted by link count across all scraped posts.
- The LLM prompt enforces that only URLs from the scraped pools are used — the model must not invent URLs.
- Image generation calls Pollinations with a random seed each time to avoid duplicate images.
- The DOCX exporter does not use `python-docx` styles that may be missing in minimal environments — it sets font properties directly on runs.
- There is no test suite. Validation is done by running the Streamlit app and testing end-to-end.
