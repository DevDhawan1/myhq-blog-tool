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

Create a `.env` file in the project root (loaded manually by `app.py` without `python-dotenv`):

```
GEMINI_API_KEY=your_key_here
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

2. **`generator.py`** — loads the scraped context and builds a large structured prompt for `gemini-2.5-flash`. The prompt feeds the model real tone samples, meta title/description examples, the full internal blog URL pool, and the top money pages. The model returns a strict JSON schema (enforced via `response_schema`) containing all SEO fields plus HTML blog content.

3. **`image_generator.py`** — generates a blog feature image via `generate_blog_image(prompt, title, api_key)`. Priority: (1) `FREE_IMAGE_API_URL` Cloudflare Worker (`https://free-image-generator-api.devanshdhawan8943.workers.dev`) — POST `{"prompt": "..."}` with `Authorization: Bearer <key>`, returns raw JPEG; (2) Pollinations.ai (free, no key) as fallback if the key is missing or the Worker fails. Raw bytes from either source are composited with a dark gradient banner and title text via Pillow. Unsplash is a last-resort fallback triggered only from `app.py` if both generate functions throw.

4. **`docx_exporter.py`** — converts the generated HTML blog content into a `.docx` via a regex-based HTML parser (`_parse_html_to_doc`). Handles `h2`, `h3`, `p`, `ul/li`, `a`, and `table` tags. Includes the feature image and an SEO metadata table.

5. **`wordpress_publisher.py`** — publishes to WordPress via the REST API (`/wp-json/wp/v2/`). `upload_media` POSTs the feature image and returns an attachment ID; `create_post` creates the post with Yoast SEO and RankMath meta fields baked into the payload. WP Application Passwords have spaces stripped internally before use.

6. **`app.py`** — orchestrates the UI. Context is loaded once at startup from cache. Blog generation, image generation, and DOCX build are triggered by user actions. Session state persists the generated result and image bytes across Streamlit rerenders.

## Key Behavioural Details

- `context_cache.json` is written relative to the script's CWD — always run the app from the project directory.
- The scraper politely sleeps 0.3s between requests and caps at `MAX_BLOGS = 1000`.
- Money pages are the top 50 most-linked `myhq.in` non-blog URLs, sorted by link count across all scraped posts.
- The Gemini prompt enforces that only URLs from the scraped pools are used — the model must not invent URLs.
- Image generation calls Pollinations with a random seed each time to avoid duplicate images.
- The DOCX exporter does not use `python-docx` styles that may be missing in minimal environments — it sets font properties directly on runs.
