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
                  override_money_pages=None, compact=False,
                  research_kb_text="", keyword_data_text=""):

    sample_count = 1 if compact else 6
    excerpt_len  = 120 if compact else 400
    tone_samples = "\n\n".join(
        f"Title: {b['title']}\nExcerpt: {b['content_preview'][:excerpt_len]}"
        for b in context["blogs"][:sample_count]
        if b.get("content_preview")
    )

    meta_limit = 3 if compact else 12
    meta_examples_text = "\n".join(
        f"  Meta title : {e['meta_title']}\n"
        f"  Meta desc  : {e['meta_desc']}"
        + (f"\n  Keywords   : {e['keywords']}" if e.get("keywords") else "")
        for e in context.get("meta_examples", [])[:meta_limit]
    )

    internal_limit = 10 if compact else len(context["blogs"])
    internal_pool = "\n".join(
        f"- {b['title']}  →  {b['url']}"
        for b in context["blogs"][:internal_limit]
        if b.get("url") and b.get("title")
    )

    money_limit = 8 if compact else 25
    mp_list = override_money_pages if override_money_pages else context["money_pages"][:money_limit]
    money_pool = "\n".join(
        f"- {mp['url']}  |  anchors: {', '.join(mp.get('anchor_texts', [])) or 'use natural anchor'}"
        for mp in mp_list
    )

    titles_limit = 8 if compact else len(context["blogs"])
    existing_titles = "\n".join(
        f"- {b['title']}" for b in context["blogs"][:titles_limit] if b.get("title")
    )

    # Optional sections
    research_section = ""
    if research_kb_text:
        research_section = f"""
══════════════════════════════════════════
RESEARCH KNOWLEDGE BASE  (use facts from these sources — cite them naturally)
══════════════════════════════════════════
{research_kb_text}
"""

    keyword_section = ""
    if keyword_data_text:
        keyword_section = f"""
══════════════════════════════════════════
KEYWORD RESEARCH  (Ahrefs data — follow these exactly)
══════════════════════════════════════════
{keyword_data_text}
"""

    return f"""You are a senior SEO content writer for myHQ — India's leading marketplace for coworking spaces, virtual offices, and managed office solutions.

══════════════════════════════════════════
TONE & STYLE REFERENCE  (match this writing style exactly)
══════════════════════════════════════════
{tone_samples}

══════════════════════════════════════════
REAL META TITLE & DESCRIPTION EXAMPLES  (study these patterns — length, style, CTA, keyword placement)
══════════════════════════════════════════
{meta_examples_text}
{research_section}{keyword_section}
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
- FAQs: End the blog with an H2 "Frequently Asked Questions" section containing exactly 5 FAQs as <h3> questions with <p> answers. Questions must be specific, high-quality, and directly relevant to the topic — not generic. Each answer must be exactly 40-60 words — this is the Google featured snippet sweet spot. Be concise and direct. FAQ answers must always be <p> paragraphs — never <ul> lists.
- TL;DR: The tl_dr field must contain exactly 5 crisp, standalone insight sentences summarising the blog's most valuable takeaways. Each must be self-contained and useful without reading the blog.
- QUICK RECAP: After the closing paragraph of EACH major H2 section (every H2 except the FAQ H2), insert exactly: <div class="quick-recap"><strong>Quick Recap:</strong> [one punchy sentence capturing that section's key point]</div>
- SCHEMA: The schema_markup field must be a valid JSON object serialised as a string (no <script> tags). Include @context, @type: Article, headline, description, author.name: myHQ Team, publisher.name: myHQ, and a keywords array of the focus + subsidiary keywords.
- WP CATEGORIES: The wp_categories field must contain 1-2 WordPress category names that best fit the topic. Choose from: Coworking Spaces, Virtual Offices, Managed Offices, Work Culture, Business Tips, Startup Guide, Remote Work, Office Space.
- DO NOT add an author section anywhere in the content — it will be injected by the publishing tool.
- WRITING STYLE — STRICT: Use short, punchy sentences (max 15 words each). One idea per sentence — never join two ideas with "and" or "but". Paragraphs must be 2-3 sentences maximum — never longer. Avoid run-on sentences and compound clauses entirely. Write like a fast-moving blog, not an essay.
- BULLET POINTS: Wherever content lists 3 or more items, features, benefits, tips, or steps — use a <ul> list instead of cramming them into a sentence or paragraph. Lists make content scannable and improve engagement.
- LLM VISIBILITY (optimise for ChatGPT / Perplexity / Gemini retrieval): Write in clear, quotable statements that AI models can extract verbatim. Use direct action verbs ("find", "use", "avoid", "choose"). Every H2 section must open with a direct answer sentence before elaborating. Structure content so a standalone paragraph answers a real user question on its own.
- AVOID AI TELLS — never use: "In today's world", "It's worth noting", "In conclusion", "As we've explored", "Delve into", "It is important to note", "Navigating the", "Game-changer", "Leverage", "Unlock", "Comprehensive". Write like an informed human journalist, not a language model.
- DIRECT ANSWER OPENINGS: Every H2 section MUST open with a single direct-answer sentence that completely answers the section's implied question on its own. This sentence should be extractable by AI search engines (Perplexity, ChatGPT, Gemini) as a standalone answer. Then elaborate in the following sentences.""" + ("" if compact else """
- DEFINITION BLOCK: Immediately after the intro paragraphs and BEFORE the first <h2>, insert a definition block: <div class="definition-box" style="background:#f0f7f0;border-left:4px solid #2d8a4e;border-radius:4px;padding:16px 20px;margin:24px 0;color:#1a1a2e;"><strong>What is [core topic]?</strong> [40-60 word clear, quotable definition targeting Google's definition featured snippet]</div>
- E-E-A-T CREDIBILITY: Reference real, named companies, products, and places (e.g. "WeWork, Regus, myHQ" not "leading providers"). Use concrete specifics (e.g. "a 10-person startup" not "teams"). Do NOT invent statistics, percentages, or survey results. If citing a well-known industry fact, attribute it vaguely ("according to industry reports") rather than fabricating a source. Never make up numbers.
- TITLE FORMULA: Pick the title pattern that best fits the topic from these proven formats: (1) Numbered: "7 Best [Topic] for [Audience] in 2025" (2) How-to: "How to [Goal] Without [Objection]" (3) Question: "What Is [Topic]? Complete Guide for [Audience]" (4) Power word: "[Power Word] Guide to [Topic]". Do NOT default to the same format every time — vary based on search intent.""")


_MAX_RETRIES = 4


def generate_blog(model, topic, word_count, keyword_density, n_internal, n_money,
                  context, override_money_pages=None,
                  research_kb_text="", keyword_data_text=""):
    prompt = _build_prompt(
        topic, word_count, keyword_density, n_internal, n_money,
        context, override_money_pages,
        research_kb_text=research_kb_text,
        keyword_data_text=keyword_data_text,
    )

    generation_config = genai.GenerationConfig(
        temperature=0.75,
        max_output_tokens=16384,
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "meta_title":          {"type": "STRING"},
                "meta_description":    {"type": "STRING"},
                "focus_keyword":       {"type": "STRING"},
                "subsidiary_keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
                "url_slug":            {"type": "STRING"},
                "blog_title":          {"type": "STRING"},
                "image_prompt":        {"type": "STRING"},
                "tl_dr":               {"type": "ARRAY", "items": {"type": "STRING"}},
                "schema_markup":       {"type": "STRING"},
                "wp_categories":       {"type": "ARRAY", "items": {"type": "STRING"}},
                "content":             {"type": "STRING"},
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
            if "PerDay" in err_str or "per_day" in err_str.lower():
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
            m = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', err_str)
            wait = int(m.group(1)) + 3 if m else 65
            print(f"[generator] Rate limit — waiting {wait}s before retry {attempt + 1}/{_MAX_RETRIES - 1}…")
            time.sleep(wait)
    else:
        raise last_exc

    result = json.loads(response.text)
    return _fix_result(result)


def _fix_result(result):
    kw   = result.get("focus_keyword", "").strip()
    desc = result.get("meta_description", "").strip()
    slug = result.get("url_slug", "").strip()

    if kw and kw.lower() not in desc.lower():
        prefix    = kw + ": "
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


def seo_quality_score(result: dict, requested_internal: int, requested_money: int,
                      target_density: float = 1.5, target_word_count: int = 1200) -> dict:
    """
    Rank Math-inspired 10-check SEO score out of 100. Target: ≥ 70 to pass.
    Each check is worth 10 points.
    """
    content = result.get("content", "")
    kw      = result.get("focus_keyword", "").strip().lower()

    text       = re.sub(r"<[^>]+>", " ", content)
    text_lower = text.lower()
    words      = text.split()
    word_count = len(words)

    checks = []

    # 1. Focus keyword in SEO title
    meta_title = result.get("meta_title", "")
    p = bool(kw and kw in meta_title.lower())
    checks.append({"name": "Keyword in SEO title", "passed": p, "points": 10,
                   "detail": "Present" if p else "Missing from meta title"})

    # 2. Focus keyword in meta description (exact phrase)
    meta_desc = result.get("meta_description", "")
    p = bool(kw and kw in meta_desc.lower())
    checks.append({"name": "Keyword in meta description", "passed": p, "points": 10,
                   "detail": f"{len(meta_desc)} chars" if p else f"Missing — {len(meta_desc)} chars"})

    # 3. Focus keyword in URL slug
    slug = result.get("url_slug", "").lower()
    kw_words = kw.split()
    p = bool(kw_words and all(w in slug for w in kw_words))
    checks.append({"name": "Keyword in URL slug", "passed": p, "points": 10,
                   "detail": slug or "—"})

    # 4. Focus keyword in first 10% of content
    first_10 = text_lower[: max(len(text_lower) // 10, 200)]
    p = bool(kw and kw in first_10)
    checks.append({"name": "Keyword in first 10% of content", "passed": p, "points": 10,
                   "detail": "Found in opening" if p else "Not in opening section"})

    # 5. Focus keyword in at least one H2 or H3
    headings = " ".join(re.findall(r"<h[23][^>]*>(.*?)</h[23]>", content, re.IGNORECASE | re.DOTALL)).lower()
    p = bool(kw and kw in headings)
    checks.append({"name": "Keyword in a heading (H2/H3)", "passed": p, "points": 10,
                   "detail": "Found in heading" if p else "Not in any H2/H3"})

    # 6. Keyword appears ≥ 4 times (density > 0 equivalent)
    kw_count = text_lower.count(kw) if kw else 0
    p = kw_count >= 4
    checks.append({"name": "Keyword density (≥4 occurrences)", "passed": p, "points": 10,
                   "detail": f"{kw_count} occurrences in ~{word_count} words"})

    # 7. Internal links present
    internal = len(re.findall(r'href=["\']https?://myhq(?:blog)?\.in/blog/', content, re.IGNORECASE))
    p = internal >= requested_internal
    checks.append({"name": "Internal links", "passed": p, "points": 10,
                   "detail": f"{internal} found (target: {requested_internal})"})

    # 8. External links (non-myhq domains)
    all_hrefs   = re.findall(r'href=["\']https?://([^/"\']+)', content)
    ext_links   = [h for h in all_hrefs if "myhq" not in h]
    p = len(ext_links) >= 1
    checks.append({"name": "External links", "passed": p, "points": 10,
                   "detail": f"{len(ext_links)} external link(s)"})

    # 9. Content ≥ 1,500 words
    p = word_count >= 1500
    checks.append({"name": "Content length ≥ 1,500 words", "passed": p, "points": 10,
                   "detail": f"~{word_count} words"})

    # 10. FAQ section present
    p = bool(re.search(r"frequently asked questions", content, re.IGNORECASE))
    checks.append({"name": "FAQ section present", "passed": p, "points": 10,
                   "detail": "FAQ found" if p else "No FAQ section"})

    score = sum(c["points"] for c in checks if c["passed"])
    return {"score": score, "max": 100, "checks": checks, "pass": score >= 70}


def generate_blog_groq(client, topic, word_count, keyword_density, n_internal, n_money,
                       context, override_money_pages=None, model_name="llama-3.3-70b-versatile",
                       research_kb_text="", keyword_data_text=""):
    groq_word_count = min(word_count, 900)
    prompt = _build_prompt(
        topic, groq_word_count, keyword_density, n_internal, n_money,
        context, override_money_pages, compact=True,
        research_kb_text=research_kb_text,
        keyword_data_text=keyword_data_text,
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.75,
        max_tokens=4096,
    )

    result = json.loads(response.choices[0].message.content)
    return _fix_result(result)
