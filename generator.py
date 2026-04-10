import google.generativeai as genai
import json
import re
import time


def setup_gemini(api_key: str, model_name: str = "gemini-2.0-flash"):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def setup_groq(api_key: str):
    from groq import Groq
    return Groq(api_key=api_key)


def _build_prompt(topic, word_count, keyword_density, n_internal, n_money, context,
                  override_money_pages=None, compact=False):
    # compact=True trims context sections to fit Groq's free-tier 12k TPM limit

    # ── Tone & style samples ──────────────────────────────────────────────────
    sample_count = 2 if compact else 6
    excerpt_len  = 200 if compact else 400
    tone_samples = "\n\n".join(
        f"Title: {b['title']}\nExcerpt: {b['content_preview'][:excerpt_len]}"
        for b in context["blogs"][:sample_count]
        if b.get("content_preview")
    )

    # ── Real meta title / description examples ────────────────────────────────
    meta_limit = 5 if compact else 12
    meta_examples_text = "\n".join(
        f"  Meta title : {e['meta_title']}\n"
        f"  Meta desc  : {e['meta_desc']}"
        + (f"\n  Keywords   : {e['keywords']}" if e.get("keywords") else "")
        for e in context.get("meta_examples", [])[:meta_limit]
    )

    # ── Internal blog link pool ───────────────────────────────────────────────
    internal_limit = 40 if compact else len(context["blogs"])
    internal_pool = "\n".join(
        f"- {b['title']}  →  {b['url']}"
        for b in context["blogs"][:internal_limit]
        if b.get("url") and b.get("title")
    )

    # ── Money pages pool ──────────────────────────────────────────────────────
    money_limit = 12 if compact else 25
    mp_list = override_money_pages if override_money_pages else context["money_pages"][:money_limit]
    money_pool = "\n".join(
        f"- {mp['url']}  |  anchors: {', '.join(mp.get('anchor_texts', [])) or 'use natural anchor'}"
        for mp in mp_list
    )

    # ── Existing titles (avoid duplication) ───────────────────────────────────
    titles_limit = 30 if compact else len(context["blogs"])
    existing_titles = "\n".join(
        f"- {b['title']}" for b in context["blogs"][:titles_limit] if b.get("title")
    )

    return f"""You are a senior SEO content writer for myHQ — India's leading marketplace for coworking spaces, virtual offices, and managed office solutions.

══════════════════════════════════════════
TONE & STYLE REFERENCE  (match this writing style exactly)
══════════════════════════════════════════
{tone_samples}

══════════════════════════════════════════
REAL META TITLE & DESCRIPTION EXAMPLES  (study these patterns — length, style, CTA, keyword placement)
══════════════════════════════════════════
{meta_examples_text}

══════════════════════════════════════════
EXISTING BLOG TITLES  (do NOT duplicate any of these)
══════════════════════════════════════════
{existing_titles}

══════════════════════════════════════════
INTERNAL BLOG LINK POOL  (weave in exactly {n_internal} of the most relevant)
══════════════════════════════════════════
{internal_pool}

══════════════════════════════════════════
MONEY PAGE LINK POOL  (weave in exactly {n_money} of the most contextually relevant)
══════════════════════════════════════════
{money_pool}

══════════════════════════════════════════
YOUR TASK
══════════════════════════════════════════
Topic            : {topic}
Word count       : ~{word_count} words (main body only)
Focus kw density : {keyword_density}% (use focus keyword naturally at this density)
Internal links   : exactly {n_internal}
Money page links : exactly {n_money}

══════════════════════════════════════════
OUTPUT — return ONLY valid JSON, zero markdown, zero preamble
══════════════════════════════════════════
{{
  "meta_title": "50-60 chars — match the style of the real examples above, includes focus keyword",
  "meta_description": "150-160 chars — compelling, ends with soft CTA, includes focus keyword, matches style of examples above",
  "focus_keyword": "primary SEO keyword phrase",
  "subsidiary_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5", "kw6"],
  "url_slug": "hyphenated-lowercase-slug",
  "blog_title": "Engaging H1 title (distinct from meta title)",
  "image_prompt": "Photorealistic scene for blog feature image — describe setting, lighting, mood, subjects in detail. No text, no logos. Professional photography style.",
  "tl_dr": ["Key insight 1 as a standalone sentence.", "Key insight 2.", "Key insight 3.", "Key insight 4.", "Key insight 5."],
  "schema_markup": "{{\"@context\":\"https://schema.org\",\"@type\":\"Article\",\"headline\":\"...\",\"description\":\"...\",\"author\":{{\"@type\":\"Person\",\"name\":\"myHQ Team\"}},\"publisher\":{{\"@type\":\"Organization\",\"name\":\"myHQ\"}},\"keywords\":[\"kw1\",\"kw2\"]}}",
  "wp_categories": ["Category Name"],
  "content": "Full blog body in clean HTML. Use <h2> and <h3> headings. Weave <a href=\\"URL\\">anchor text</a> links naturally mid-paragraph. Do NOT include the H1 title in the content body. Target ~{word_count} words."
}}

Rules:
- Links must feel completely natural — never forced or listed at the end
- Anchor text must be descriptive and 4-7 words long — never just 2 words. Use meaningful phrases that describe the destination page (e.g. "best coworking spaces in Bangalore" not just "coworking spaces")
- Match myHQ's tone and vocabulary from the reference samples
- FOCUS KEYWORD IN URL: The url_slug MUST contain every word of the focus keyword, hyphenated. e.g. if focus keyword is "coworking spaces Chennai", slug must include "coworking-spaces-chennai"
- FOCUS KEYWORD AT START: The very first sentence of the content body MUST contain the focus keyword. Do not open with a generic statement — lead with the keyword naturally.
- KEYWORD DENSITY: For a ~{word_count} word blog at {keyword_density}%, the focus keyword must appear approximately {int(round(word_count * keyword_density / 100))} times. Count carefully and distribute the keyword naturally throughout paragraphs, headings, and the FAQ section.
- META TITLE POWER WORD: The meta_title MUST contain at least one power word from this list: Ultimate, Complete, Best, Top, Essential, Proven, Expert, Simple, Free, New, Definitive, Perfect, Effective, Smart, Right. Place the power word early in the title.
- META DESCRIPTION KEYWORD: The meta_description MUST contain the exact focus keyword phrase, ideally within the first half of the description.
- Subsidiary keywords should each appear at least once
- Only use URLs that appear in the pools above — do not invent URLs
- Internal blog URLs must be in the format: https://myhq.in/blog/...
- Money page URLs must be in the format: https://myhq.in/... (not /blog/)
- MONEY PAGE LINKS: Place at least one money page link naturally within the first two paragraphs of the content
- TABLE: If the topic suits a comparison, feature list, or pricing overview, include one HTML <table> with <thead> and <tbody> in the second major H2 section of the blog
- FAQs: End the blog with an H2 "Frequently Asked Questions" section containing exactly 5 FAQs as <h3> questions with <p> answers. Questions must be specific, high-quality, and directly relevant to the topic — not generic. Answers should be 2-3 short sentences each. FAQ answers must always be <p> paragraphs — never <ul> lists.
- TL;DR: The tl_dr field must contain exactly 5 crisp, standalone insight sentences summarising the blog's most valuable takeaways. Each must be self-contained and useful without reading the blog.
- QUICK RECAP: After the closing paragraph of EACH major H2 section (every H2 except the FAQ H2), insert exactly: <div class="quick-recap"><strong>Quick Recap:</strong> [one punchy sentence capturing that section's key point]</div>
- SCHEMA: The schema_markup field must be a valid JSON object serialised as a string (no <script> tags). Include @context, @type: Article, headline, description, author.name: myHQ Team, publisher.name: myHQ, and a keywords array of the focus + subsidiary keywords.
- WP CATEGORIES: The wp_categories field must contain 1-2 WordPress category names that best fit the topic. Choose from: Coworking Spaces, Virtual Offices, Managed Offices, Work Culture, Business Tips, Startup Guide, Remote Work, Office Space.
- DO NOT add an author section anywhere in the content — it will be injected by the publishing tool.
- WRITING STYLE — STRICT: Use short, punchy sentences (max 15 words each). One idea per sentence — never join two ideas with "and" or "but". Paragraphs must be 2-3 sentences maximum — never longer. Avoid run-on sentences and compound clauses entirely. Write like a fast-moving blog, not an essay.
- BULLET POINTS: Wherever content lists 3 or more items, features, benefits, tips, or steps — use a <ul> list instead of cramming them into a sentence or paragraph. Lists make content scannable and improve engagement.
- LLM VISIBILITY (optimise for ChatGPT / Perplexity / Gemini retrieval): Write in clear, quotable statements that AI models can extract verbatim. Use direct action verbs ("find", "use", "avoid", "choose"). Every H2 section must open with a direct answer sentence before elaborating. Structure content so a standalone paragraph answers a real user question on its own.
- AVOID AI TELLS — never use: "In today's world", "It's worth noting", "In conclusion", "As we've explored", "Delve into", "It is important to note", "Navigating the", "Game-changer", "Leverage", "Unlock", "Comprehensive". Write like an informed human journalist, not a language model."""


_MAX_RETRIES = 4


def generate_blog(model, topic, word_count, keyword_density, n_internal, n_money,
                  context, override_money_pages=None):
    prompt = _build_prompt(
        topic, word_count, keyword_density, n_internal, n_money,
        context, override_money_pages,
    )

    generation_config = genai.GenerationConfig(
        temperature=0.75,
        max_output_tokens=16384,
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "meta_title":           {"type": "STRING"},
                "meta_description":     {"type": "STRING"},
                "focus_keyword":        {"type": "STRING"},
                "subsidiary_keywords":  {"type": "ARRAY", "items": {"type": "STRING"}},
                "url_slug":             {"type": "STRING"},
                "blog_title":           {"type": "STRING"},
                "image_prompt":         {"type": "STRING"},
                "tl_dr":               {"type": "ARRAY", "items": {"type": "STRING"}},
                "schema_markup":        {"type": "STRING"},
                "wp_categories":        {"type": "ARRAY", "items": {"type": "STRING"}},
                "content":              {"type": "STRING"},
            },
            "required": [
                "meta_title", "meta_description", "focus_keyword",
                "subsidiary_keywords", "url_slug", "blog_title",
                "image_prompt", "tl_dr", "schema_markup", "wp_categories", "content",
            ],
        },
    )

    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = model.generate_content(prompt, generation_config=generation_config)
            break
        except Exception as e:
            last_exc = e
            err_str = str(e)
            is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "ResourceExhausted" in type(e).__name__
            if not is_rate_limit:
                raise
            # Daily quota is exhausted — retrying won't help
            if "PerDay" in err_str or "per_day" in err_str.lower():
                # Extract model and quota_value from the raw error for a precise message
                model_m = re.search(r'value:\s*"([^"]+)"', err_str)
                quota_m = re.search(r'quota_value:\s*(\d+)', err_str)
                model_str = model_m.group(1) if model_m else "this model"
                quota_str = f"{quota_m.group(1)} requests/day" if quota_m else "the daily limit"
                raise RuntimeError(
                    f"Gemini free-tier daily quota exhausted for {model_str} ({quota_str}). "
                    "The quota resets at midnight Pacific time. "
                    "To remove this limit, add billing to your Google AI Studio project."
                ) from e
            if attempt == _MAX_RETRIES - 1:
                raise
            # Per-minute rate limit — wait and retry
            m = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', err_str)
            wait = int(m.group(1)) + 3 if m else 65
            print(f"[generator] Rate limit hit — waiting {wait}s before retry {attempt + 1}/{_MAX_RETRIES - 1}...")
            time.sleep(wait)
    else:
        raise last_exc

    result = json.loads(response.text)

    # ── Post-generation validation & hard fixes ───────────────────────────────
    kw   = result.get("focus_keyword", "").strip()
    desc = result.get("meta_description", "").strip()
    slug = result.get("url_slug", "").strip()

    # 1. Force focus keyword into meta description if missing
    if kw and kw.lower() not in desc.lower():
        prefix = kw + ": "
        available = 157 - len(prefix)          # leave 3 for "..."
        if available >= 20:
            # Trim existing desc to fit after the prefix
            trimmed = desc[:available].rsplit(" ", 1)[0]  # break on word boundary
            result["meta_description"] = prefix + trimmed + "..."
        else:
            # Focus keyword itself is very long — just use it as the description seed
            result["meta_description"] = (prefix + desc)[:160]

    # 2. Force focus keyword words into URL slug if missing
    if kw:
        kw_slug = kw.lower().replace(" ", "-")
        if kw_slug not in slug:
            result["url_slug"] = kw_slug

    return result


def _fix_result(result):
    """Post-generation validation shared across providers."""
    kw   = result.get("focus_keyword", "").strip()
    desc = result.get("meta_description", "").strip()
    slug = result.get("url_slug", "").strip()

    if kw and kw.lower() not in desc.lower():
        prefix = kw + ": "
        available = 157 - len(prefix)
        if available >= 20:
            trimmed = desc[:available].rsplit(" ", 1)[0]
            result["meta_description"] = prefix + trimmed + "..."
        else:
            result["meta_description"] = (prefix + desc)[:160]

    if kw:
        kw_slug = kw.lower().replace(" ", "-")
        if kw_slug not in slug:
            result["url_slug"] = kw_slug

    return result


def generate_blog_groq(client, topic, word_count, keyword_density, n_internal, n_money,
                       context, override_money_pages=None, model_name="llama-3.3-70b-versatile"):
    prompt = _build_prompt(
        topic, word_count, keyword_density, n_internal, n_money,
        context, override_money_pages, compact=True,
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.75,
        max_tokens=8192,
    )

    result = json.loads(response.choices[0].message.content)
    return _fix_result(result)
