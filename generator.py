import google.generativeai as genai
import json
import re


def setup_gemini(api_key: str):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")


def _build_prompt(topic, word_count, keyword_density, n_internal, n_money, context, override_money_pages=None):

    # ── Tone & style samples (first 6 blogs) ──────────────────────────────────
    tone_samples = "\n\n".join(
        f"Title: {b['title']}\nExcerpt: {b['content_preview'][:400]}"
        for b in context["blogs"][:6]
        if b.get("content_preview")
    )

    # ── Real meta title / description examples ────────────────────────────────
    meta_examples_text = "\n".join(
        f"  Meta title : {e['meta_title']}\n"
        f"  Meta desc  : {e['meta_desc']}"
        + (f"\n  Keywords   : {e['keywords']}" if e.get("keywords") else "")
        for e in context.get("meta_examples", [])[:12]
    )

    # ── Internal blog link pool ───────────────────────────────────────────────
    internal_pool = "\n".join(
        f"- {b['title']}  →  {b['url']}"
        for b in context["blogs"]
        if b.get("url") and b.get("title")
    )

    # ── Money pages pool ──────────────────────────────────────────────────────
    mp_list = override_money_pages if override_money_pages else context["money_pages"][:25]
    money_pool = "\n".join(
        f"- {mp['url']}  |  anchors: {', '.join(mp.get('anchor_texts', [])) or 'use natural anchor'}"
        for mp in mp_list
    )

    # ── Existing titles (avoid duplication) ───────────────────────────────────
    existing_titles = "\n".join(
        f"- {b['title']}" for b in context["blogs"] if b.get("title")
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
  "content": "Full blog body in clean HTML. Use <h2> and <h3> headings. Weave <a href=\\"URL\\">anchor text</a> links naturally mid-paragraph. Do NOT include the H1 title in the content body. Target ~{word_count} words."
}}

Rules:
- Links must feel completely natural — never forced or listed at the end
- Match myHQ's tone and vocabulary from the reference samples
- Focus keyword must appear in: first 100 words, at least one H2, and naturally throughout at {keyword_density}% density
- Subsidiary keywords should each appear at least once
- Only use URLs that appear in the pools above — do not invent URLs
- Internal blog URLs must be in the format: https://myhq.in/blog/...
- Money page URLs must be in the format: https://myhq.in/... (not /blog/)
- MONEY PAGE LINKS: Place at least one money page link naturally within the first two paragraphs of the content
- TABLE: If the topic suits a comparison, feature list, or pricing overview, include one HTML <table> with <thead> and <tbody> in the second major H2 section of the blog
- FAQs: End the blog with an H2 "Frequently Asked Questions" section containing exactly 5 FAQs as <h3> questions with <p> answers. Questions must be specific, high-quality, and directly relevant to the topic — not generic. Answers should be 2-3 sentences each."""


def generate_blog(model, topic, word_count, keyword_density, n_internal, n_money,
                  context, override_money_pages=None):
    prompt = _build_prompt(
        topic, word_count, keyword_density, n_internal, n_money,
        context, override_money_pages,
    )

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
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
                    "content":              {"type": "STRING"},
                },
                "required": [
                    "meta_title", "meta_description", "focus_keyword",
                    "subsidiary_keywords", "url_slug", "blog_title",
                    "image_prompt", "content",
                ],
            },
        ),
    )

    return json.loads(response.text)
