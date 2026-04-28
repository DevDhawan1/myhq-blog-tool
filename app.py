import streamlit as st
import json
import os
from datetime import datetime

# Read .env manually — no library dependency, works regardless of CWD or encoding
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip()
                if _k and _v:
                    os.environ[_k] = _v

from scraper import build_context, load_context
from generator import setup_gemini, generate_blog, setup_groq, generate_blog_groq, seo_quality_score
from image_generator import generate_blog_image, get_unsplash_image
from docx_exporter import build_docx
from wordpress_publisher import upload_media, create_post
from researcher import build_research_kb, format_kb_for_prompt
from keyword_researcher import get_keyword_ideas, format_keyword_data_for_prompt
from humanizer import humanize_content
from tracker import append_tracking_row, ensure_headers


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="myHQ Blog Drafting Tool",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.kw-chip  { display:inline-block; background:#e8f4fd; color:#1a73e8;
            border-radius:16px; padding:3px 12px; margin:3px; font-size:13px; }
.char-ok  { color:#2d8a4e; font-size:12px; }
.char-bad { color:#c0392b; font-size:12px; }
.seo-pass { background:#e8f5e9; border-left:4px solid #2d8a4e; padding:10px 14px;
            border-radius:4px; margin:4px 0; font-size:13px; }
.seo-fail { background:#fdecea; border-left:4px solid #c0392b; padding:10px 14px;
            border-radius:4px; margin:4px 0; font-size:13px; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    try:
        st.image(
            "https://play-lh.googleusercontent.com/IYnsXC7SsNBIPKq1XMMfiWdPrdbd9IlTHl1cDaBHAITTVOVIyUyUAUm6vsN7IDRtgEw",
            width=100,
        )
    except Exception:
        st.markdown("### myHQ")

    st.title("Settings")

    # ── LLM Provider ─────────────────────────────────────────────────────────
    st.subheader("API Keys")

    llm_provider = st.selectbox(
        "LLM Provider",
        options=["Groq (free, 14,400/day)", "Gemini"],
        index=0,
    )
    st.session_state["llm_provider"] = llm_provider

    if "Groq" in llm_provider:
        groq_key = st.text_input(
            "Groq API Key  *(required)*",
            value=st.session_state.get("groq_api_key", os.environ.get("GROQ_API_KEY", "")),
            type="password",
        )
        st.session_state["groq_api_key"] = groq_key
        if groq_key:
            os.environ["GROQ_API_KEY"] = groq_key
        api_key = groq_key
    else:
        api_key = st.text_input(
            "Gemini API Key  *(required)*",
            value=st.session_state.get("gemini_api_key", os.environ.get("GEMINI_API_KEY", "")),
            type="password",
        )
        st.session_state["gemini_api_key"] = api_key
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key

        gemini_model = st.selectbox(
            "Gemini Model",
            options=["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"],
            index=0,
        )
        st.session_state["gemini_model"] = gemini_model

    # ── Ahrefs ────────────────────────────────────────────────────────────────
    ahrefs_key = st.text_input(
        "Ahrefs API Key  *(keyword research)*",
        value=st.session_state.get("ahrefs_api_key", os.environ.get("AHREFS_API_KEY", "")),
        type="password",
        help="Optional. Enables automatic keyword research via Ahrefs matching-terms API.",
    )
    st.session_state["ahrefs_api_key"] = ahrefs_key
    if ahrefs_key:
        os.environ["AHREFS_API_KEY"] = ahrefs_key

    # ── Image API ────────────────────────────────────────────────────────────
    free_image_api_key = st.text_input(
        "Image API Key  *(primary)*",
        value=st.session_state.get("free_image_api_key", os.environ.get("FREE_IMAGE_API_KEY", "")),
        type="password",
    )
    st.session_state["free_image_api_key"] = free_image_api_key
    if free_image_api_key:
        os.environ["FREE_IMAGE_API_KEY"] = free_image_api_key

    unsplash_key = st.text_input(
        "Unsplash Key  *(last-resort fallback)*",
        value=st.session_state.get("unsplash_key", os.environ.get("UNSPLASH_ACCESS_KEY", "")),
        type="password",
    )
    st.session_state["unsplash_key"] = unsplash_key
    if unsplash_key:
        os.environ["UNSPLASH_ACCESS_KEY"] = unsplash_key

    st.divider()

    # ── WordPress ────────────────────────────────────────────────────────────
    st.subheader("WordPress")
    st.caption("Required to publish directly to WP.")

    wp_site_url = st.text_input(
        "WP Site URL",
        value=st.session_state.get("wp_site_url", os.environ.get("WP_SITE_URL", "")),
        placeholder="https://myhqblog.in",
    )
    st.session_state["wp_site_url"] = wp_site_url
    if wp_site_url:
        os.environ["WP_SITE_URL"] = wp_site_url

    wp_username = st.text_input(
        "WP Username",
        value=st.session_state.get("wp_username", os.environ.get("WP_USERNAME", "")),
    )
    st.session_state["wp_username"] = wp_username
    if wp_username:
        os.environ["WP_USERNAME"] = wp_username

    wp_app_password = st.text_input(
        "WP Application Password",
        value=st.session_state.get("wp_app_password", os.environ.get("WP_APP_PASSWORD", "")),
        type="password",
    )
    st.session_state["wp_app_password"] = wp_app_password
    if wp_app_password:
        os.environ["WP_APP_PASSWORD"] = wp_app_password

    st.divider()

    # ── Google Sheets Tracker ─────────────────────────────────────────────────
    st.subheader("Publishing Tracker")
    st.caption("Google Sheets integration for tracking published posts.")

    gc_file = st.text_input(
        "Credentials JSON path",
        value=st.session_state.get("gc_file", os.environ.get("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")),
        placeholder="google_credentials.json",
        help="Path to your Google service account JSON file.",
    )
    st.session_state["gc_file"] = gc_file
    if gc_file:
        os.environ["GOOGLE_CREDENTIALS_FILE"] = gc_file

    tracking_sheet_url = st.text_input(
        "Tracking Sheet URL",
        value=st.session_state.get("tracking_sheet_url", os.environ.get("TRACKING_SHEET_URL", "")),
        placeholder="https://docs.google.com/spreadsheets/d/...",
    )
    st.session_state["tracking_sheet_url"] = tracking_sheet_url
    if tracking_sheet_url:
        os.environ["TRACKING_SHEET_URL"] = tracking_sheet_url

    _tracker_ready = (
        gc_file
        and os.path.exists(gc_file)
        and tracking_sheet_url
    )
    if _tracker_ready:
        st.success("Tracker connected")
        st.markdown(f"[Open Tracker Sheet]({tracking_sheet_url})")
    elif gc_file or tracking_sheet_url:
        st.warning("Add both credentials file and sheet URL to enable tracking.")

    st.divider()

    # ── Author ────────────────────────────────────────────────────────────────
    st.subheader("Author")
    author_name = st.text_input(
        "Author Name",
        value=st.session_state.get("author_name", os.environ.get("AUTHOR_NAME", "myHQ Team")),
    )
    st.session_state["author_name"] = author_name

    author_role = st.text_input(
        "Author Role",
        value=st.session_state.get("author_role", os.environ.get("AUTHOR_ROLE", "Content Team")),
    )
    st.session_state["author_role"] = author_role

    author_avatar_url = st.text_input(
        "Author Avatar URL  *(optional)*",
        value=st.session_state.get("author_avatar_url", os.environ.get("AUTHOR_AVATAR_URL", "")),
        placeholder="https://myhq.in/author-avatar.jpg",
    )
    st.session_state["author_avatar_url"] = author_avatar_url

    st.divider()

    # ── Blog Context ──────────────────────────────────────────────────────────
    st.subheader("Blog Context")

    context = load_context()
    if context:
        scraped_date = context.get("scraped_at", "")[:10]
        st.success(f"{context['total_blogs']} blogs indexed")
        st.caption(f"Last refreshed: {scraped_date}")
    else:
        st.warning("Context not loaded. Click Refresh below.")

    if st.button("Refresh Context", use_container_width=True,
                 help="Fetches all posts via WP REST API (~30 sec) and scrapes 6 tone samples from myhq.in/blog/."):
        prog   = st.progress(0)
        status = st.empty()

        def _cb(pct, msg):
            prog.progress(pct)
            status.caption(msg)

        with st.spinner("Fetching posts via WP REST API…"):
            try:
                context = build_context(progress_callback=_cb)
                prog.progress(1.0)
                status.caption("Done!")
                st.success(f"Indexed {context['total_blogs']} posts")
                st.rerun()
            except Exception as e:
                st.error(f"Context refresh failed: {e}")

    if context and st.checkbox("Show money pages"):
        st.caption("Virtual Office, Coworking, Managed Office, Bare Shell pages:")
        for mp in context.get("money_pages", [])[:15]:
            anchors = ", ".join(mp.get("anchor_texts", [])[:2])
            st.caption(f"• {mp['url']}  —  {anchors}")


# ── Main ──────────────────────────────────────────────────────────────────────
st.title("myHQ Blog Drafting Tool")
st.caption("SEO blog generation · Ahrefs keywords · Research KB · Humanizer · WordPress publishing")

if not context:
    st.info("Click **Refresh Context** in the sidebar to load blog data.")
    st.stop()

# ── Input form ────────────────────────────────────────────────────────────────
with st.form("blog_form"):
    st.subheader("Blog Parameters")

    col1, col2 = st.columns([3, 2])
    with col1:
        topic = st.text_input(
            "Blog Topic *",
            placeholder="e.g. Benefits of virtual offices for startups in Bangalore",
        )
    with col2:
        word_count = st.number_input(
            "Word Count *", min_value=300, max_value=5000, value=1500, step=100
        )

    col3, col4, col5 = st.columns(3)
    with col3:
        keyword_density = st.slider("Keyword Density (%)", 0.5, 3.0, 1.5, 0.1)
    with col4:
        n_internal = st.number_input("Internal Blog Links", min_value=0, max_value=10, value=3)
    with col5:
        n_money = st.number_input("Money Page Links", min_value=0, max_value=10, value=2)

    blog_category = st.radio(
        "Blog Category *",
        options=["Office Space", "Virtual Office", "Managed Office", "Business Hubs"],
        horizontal=True,
    )

    with st.expander("Reference URLs for research  (optional)"):
        st.caption("Paste authoritative URLs (one per line). The tool will fetch and extract key facts from each before generating.")
        reference_urls_raw = st.text_area(
            "Reference URLs",
            height=100,
            placeholder="https://cbic.gov.in/...\nhttps://cleartax.in/...",
            label_visibility="collapsed",
        )

    with st.expander("Override money pages  (optional)"):
        st.caption("Paste specific money page URLs (one per line) to use instead of auto-detected ones.")
        override_raw = st.text_area(
            "Custom money page URLs",
            height=90,
            placeholder="https://myhq.in/coworking-spaces/bangalore\nhttps://myhq.in/virtual-office/delhi",
            label_visibility="collapsed",
        )

    apply_humanizer = st.checkbox(
        "Apply Humanizer after generation",
        value=True,
        help="Runs a second LLM pass to remove AI writing patterns (em dashes, AI vocabulary, title-case headings, etc.)",
    )

    submitted = st.form_submit_button("Generate Blog Draft", type="primary", use_container_width=True)


# ── Trigger generation ────────────────────────────────────────────────────────
if submitted:
    _provider = st.session_state.get("llm_provider", "Groq (free, 14,400/day)")
    if not api_key:
        st.error(f"Enter your {'Groq' if 'Groq' in _provider else 'Gemini'} API key in the sidebar.")
        st.stop()
    if not topic.strip():
        st.error("Please enter a blog topic.")
        st.stop()

    override_money = None
    if override_raw.strip():
        override_money = [
            {"url": u.strip(), "anchor_texts": [], "link_count": 0}
            for u in override_raw.strip().splitlines() if u.strip()
        ]

    # ── Step 1: Keyword research ──────────────────────────────────────────────
    kw_data      = None
    kw_data_text = ""
    _ahrefs_key  = st.session_state.get("ahrefs_api_key", "")
    if _ahrefs_key:
        with st.spinner("Researching keywords via Ahrefs…"):
            try:
                kw_data      = get_keyword_ideas(_ahrefs_key, topic)
                kw_data_text = format_keyword_data_for_prompt(kw_data)
            except Exception as e:
                st.warning(f"Keyword research failed ({e}) — continuing without Ahrefs data.")

    # ── Step 2: Research KB ───────────────────────────────────────────────────
    research_kb      = None
    research_kb_text = ""
    ref_urls = [u.strip() for u in reference_urls_raw.strip().splitlines() if u.strip()] if reference_urls_raw.strip() else []
    if ref_urls:
        with st.spinner(f"Fetching {len(ref_urls)} reference source(s)…"):
            try:
                research_kb      = build_research_kb(ref_urls, topic)
                research_kb_text = format_kb_for_prompt(research_kb)
            except Exception as e:
                st.warning(f"Research fetch failed ({e}) — continuing without KB.")

    # ── Step 3: Generate ─────────────────────────────────────────────────────
    _spinner_msg = (
        "Asking Groq (Llama 3.3 70B) to write your blog…"
        if "Groq" in _provider
        else "Asking Gemini to write your blog…"
    )
    with st.spinner(_spinner_msg):
        try:
            if "Groq" in _provider:
                client = setup_groq(api_key)
                result = generate_blog_groq(
                    client, topic, word_count, keyword_density,
                    n_internal, n_money, context, override_money,
                    research_kb_text=research_kb_text,
                    keyword_data_text=kw_data_text,
                )
            else:
                model = setup_gemini(api_key, st.session_state.get("gemini_model", "gemini-2.0-flash"))
                result = generate_blog(
                    model, topic, word_count, keyword_density,
                    n_internal, n_money, context, override_money,
                    research_kb_text=research_kb_text,
                    keyword_data_text=kw_data_text,
                )
        except Exception as e:
            st.error(f"Generation error: {e}")
            st.stop()

    # ── Step 4: Humanize ─────────────────────────────────────────────────────
    if apply_humanizer:
        with st.spinner("Humanizing content…"):
            try:
                result["content"] = humanize_content(
                    result["content"],
                    provider=_provider,
                    api_key=api_key,
                    model=st.session_state.get("gemini_model", "gemini-2.0-flash"),
                )
            except Exception as e:
                st.warning(f"Humanizer failed ({e}) — using raw generated content.")

    # ── Persist state ─────────────────────────────────────────────────────────
    st.session_state["result"]          = result
    st.session_state["blog_category"]   = blog_category
    st.session_state["generated_at"]    = datetime.now().strftime("%d %b %Y, %H:%M")
    st.session_state["kw_data"]         = kw_data
    st.session_state["seo_score"]       = seo_quality_score(result, n_internal, n_money, keyword_density, word_count)
    st.session_state["img_bytes"]       = None
    st.session_state["img_url"]         = None
    st.session_state["img_credit"]      = None
    st.session_state["wp_publish_result"] = None
    st.session_state["docx_auto_saved"] = False
    st.session_state["docx_save_path"]  = None


# ── Display result ─────────────────────────────────────────────────────────────
if "result" not in st.session_state:
    st.stop()

result = st.session_state["result"]
st.divider()

hcol, tcol = st.columns([4, 1])
with hcol:
    st.subheader("Blog Draft")
with tcol:
    st.caption(f"Generated: {st.session_state.get('generated_at', '')}")

# ── Feature image ─────────────────────────────────────────────────────────────
st.markdown("#### Feature Image")
blog_title   = result.get("blog_title", topic)
unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")

if st.session_state.get("img_bytes") is None:
    _api_key = os.environ.get("FREE_IMAGE_API_KEY", "")
    with st.spinner("Generating feature image… (20–40 sec)"):
        try:
            img_bytes = generate_blog_image(blog_title, api_key=_api_key)
            st.session_state["img_bytes"]  = img_bytes
            st.session_state["img_url"]    = ""
            st.session_state["img_credit"] = (
                "Generated with free-image-generator-api" if _api_key
                else "Generated with Pollinations.ai · Flux Realism"
            )
        except Exception as e:
            st.warning(f"Image generation failed: {e}. Falling back to Unsplash.")
            st.session_state["img_bytes"] = b""

    if not st.session_state.get("img_bytes") and unsplash_key:
        with st.spinner("Fetching image from Unsplash…"):
            img_url, img_credit = get_unsplash_image(blog_title, unsplash_key)
            st.session_state["img_url"]    = img_url
            st.session_state["img_credit"] = img_credit
            if img_url:
                try:
                    import requests as _req
                    r = _req.get(img_url, timeout=15)
                    st.session_state["img_bytes"] = r.content if r.ok else b""
                except Exception:
                    st.session_state["img_bytes"] = b""

img_bytes  = st.session_state.get("img_bytes", b"")
img_url    = st.session_state.get("img_url", "")
img_credit = st.session_state.get("img_credit", "")

if img_bytes:
    st.image(img_bytes, use_container_width=True)
    st.caption(
        ("Source: free-image-generator-api" if os.environ.get("FREE_IMAGE_API_KEY") else "Source: Pollinations.ai")
        + (f"  |  {img_credit}" if img_credit else "")
    )
elif img_url:
    st.image(img_url, use_container_width=True)
    if img_credit:
        st.caption(img_credit)
else:
    st.info("Image generation failed. Add an Unsplash key in the sidebar as a fallback.")

# ── Keyword research results ──────────────────────────────────────────────────
kw_data = st.session_state.get("kw_data")
if kw_data and kw_data.get("primary"):
    with st.expander("Keyword Research (Ahrefs)"):
        p = kw_data["primary"]
        st.markdown(
            f"**Primary:** `{p.get('keyword')}` — "
            f"Vol: **{p.get('volume', '—')}** | KD: **{p.get('difficulty', '—')}** | TP: **{p.get('traffic_potential', '—')}**"
        )
        if kw_data.get("secondaries"):
            st.markdown("**Secondary keywords:**")
            for s in kw_data["secondaries"]:
                st.caption(f"• {s.get('keyword')}  —  Vol: {s.get('volume', '—')} | KD: {s.get('difficulty', '—')}")

# ── SEO metadata ──────────────────────────────────────────────────────────────
st.markdown("#### SEO Metadata")

mc1, mc2 = st.columns(2)
with mc1:
    meta_title = result.get("meta_title", "")
    st.markdown("**Meta Title**")
    st.code(meta_title, language=None)
    mtc = len(meta_title)
    st.markdown(
        f'<span class="{"char-ok" if mtc <= 60 else "char-bad"}">{mtc} / 60 chars</span>',
        unsafe_allow_html=True,
    )
    st.markdown("**Focus Keyword**")
    st.code(result.get("focus_keyword", ""), language=None)
    st.markdown("**URL Slug**")
    st.code(result.get("url_slug", ""), language=None)

with mc2:
    meta_desc = result.get("meta_description", "")
    st.markdown("**Meta Description**")
    st.text_area("", meta_desc, height=100, key="meta_desc_box", label_visibility="collapsed")
    mdc = len(meta_desc)
    st.markdown(
        f'<span class="{"char-ok" if mdc <= 160 else "char-bad"}">{mdc} / 160 chars</span>',
        unsafe_allow_html=True,
    )
    st.markdown("**Subsidiary Keywords**")
    chips = " ".join(
        f'<span class="kw-chip">{kw}</span>'
        for kw in result.get("subsidiary_keywords", [])
    )
    st.markdown(chips, unsafe_allow_html=True)

# ── SEO Score (Rank Math ≥70) ─────────────────────────────────────────────────
seo_score_data = st.session_state.get("seo_score")
if seo_score_data:
    _sc = seo_score_data["score"]
    _pass = seo_score_data.get("pass", False)
    if _pass:
        _color, _label = "#2d8a4e", f"PASS — {_sc}/100"
    elif _sc >= 50:
        _color, _label = "#d4a017", f"NEEDS WORK — {_sc}/100"
    else:
        _color, _label = "#c0392b", f"FAIL — {_sc}/100"

    with st.expander(f"Rank Math SEO Score: {_label}  (target ≥ 70)"):
        for check in seo_score_data["checks"]:
            css = "seo-pass" if check["passed"] else "seo-fail"
            icon = "✅" if check["passed"] else "❌"
            st.markdown(
                f'<div class="{css}">{icon} <strong>{check["name"]}</strong> — {check["detail"]} (+{check["points"]} pts)</div>',
                unsafe_allow_html=True,
            )

# ── Build enriched content (TL;DR injected before first H2) ──────────────────
tl_dr = result.get("tl_dr", [])
_raw_content = result.get("content", "")

if tl_dr:
    _bullets = "".join(f"<li>{item}</li>" for item in tl_dr)
    _tldr_html = (
        '<div class="tldr-box" style="background:#e8f4fd;border-left:4px solid #1a73e8;'
        'border-radius:4px;padding:16px 20px;margin:24px 0;color:#1a1a2e;">'
        '<strong style="color:#1a1a2e;">Key Takeaways</strong>'
        f'<ul style="margin:8px 0 0;padding-left:20px;color:#1a1a2e;">{_bullets}</ul>'
        '</div>'
    )
    _insert_at = _raw_content.find("<h2")
    enriched_content = (
        _raw_content[:_insert_at] + _tldr_html + "\n" + _raw_content[_insert_at:]
        if _insert_at != -1
        else _tldr_html + "\n" + _raw_content
    )
else:
    enriched_content = _raw_content

schema_str = result.get("schema_markup", "")
if schema_str:
    with st.expander("JSON-LD Schema Markup"):
        try:
            st.code(json.dumps(json.loads(schema_str), indent=2), language="json")
        except Exception:
            st.code(schema_str, language="json")

# ── Blog content ───────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"## {result.get('blog_title', '')}")

tab_preview, tab_html = st.tabs(["Rendered Preview", "Raw HTML"])
with tab_preview:
    st.markdown(enriched_content, unsafe_allow_html=True)
with tab_html:
    st.text_area("", enriched_content, height=450, key="raw_html_box", label_visibility="collapsed")

# ── Downloads ──────────────────────────────────────────────────────────────────
st.divider()
st.markdown("#### Download Draft")

slug       = result.get("url_slug", "blog-draft")
full_draft = {"generated_at": st.session_state.get("generated_at", ""), **result}

if st.session_state.get("docx_save_path"):
    st.info(f"Auto-saved: `{st.session_state['docx_save_path']}`")

dl1, dl2 = st.columns(2)

with dl1:
    with st.spinner("Building .docx…"):
        try:
            docx_bytes = build_docx(result, img_bytes if img_bytes else None)
            if not st.session_state.get("docx_auto_saved"):
                _dl_dir   = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(_dl_dir, exist_ok=True)
                _save_path = os.path.join(_dl_dir, f"{slug}.docx")
                with open(_save_path, "wb") as _fh:
                    _fh.write(docx_bytes)
                st.session_state["docx_auto_saved"] = True
                st.session_state["docx_save_path"]  = _save_path
            st.download_button(
                "Download Word Document (.docx)",
                data=docx_bytes,
                file_name=f"{slug}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as e:
            st.warning(f"DOCX build failed: {e}")

with dl2:
    st.download_button(
        "Download JSON (all fields)",
        data=json.dumps(full_draft, indent=2, ensure_ascii=False),
        file_name=f"{slug}.json",
        mime="application/json",
        use_container_width=True,
    )

# ── Publish to WordPress ───────────────────────────────────────────────────────
st.divider()
st.markdown("#### Publish to WordPress")

_wp_url  = st.session_state.get("wp_site_url", "")
_wp_user = st.session_state.get("wp_username", "")
_wp_pass = st.session_state.get("wp_app_password", "")

if not (_wp_url and _wp_user and _wp_pass):
    st.info("Enter WordPress credentials in the sidebar to enable publishing.")
else:
    wp_status_choice = st.selectbox(
        "Publish status",
        options=["Draft", "Publish Live"],
        index=0,
    )
    wp_status_value    = "draft" if wp_status_choice == "Draft" else "publish"
    _selected_category = st.session_state.get("blog_category", "Office Space")
    st.caption(f"Category: **{_selected_category}**")

    # Tags from subsidiary keywords
    _sub_kws = result.get("subsidiary_keywords", [])
    _focus_kw = result.get("focus_keyword", "")
    _default_tags = ", ".join([_focus_kw] + _sub_kws[:4]) if _focus_kw else ""
    tags_input = st.text_input(
        "Tags (comma-separated)",
        value=_default_tags,
        help="Pre-filled from focus + subsidiary keywords. Edit as needed.",
    )

    if st.button("Publish to WordPress", type="primary"):
        _img_bytes = st.session_state.get("img_bytes") or b""

        with st.spinner("Publishing to WordPress…"):
            try:
                # Upload featured image
                media_id, media_url = 0, ""
                if _img_bytes:
                    try:
                        _media   = upload_media(
                            site_url=_wp_url, username=_wp_user, app_password=_wp_pass,
                            image_bytes=_img_bytes,
                            filename=f"{result.get('url_slug', 'feature-image')}.png",
                            alt_text=f"{result.get('focus_keyword', '')} – {blog_title}".strip(" –"),
                        )
                        media_id  = _media["id"]
                        media_url = _media["url"]
                    except Exception as img_err:
                        st.warning(f"Image upload failed ({img_err}) — post created without featured image.")

                # Build author block
                _author_name   = st.session_state.get("author_name", "myHQ Team")
                _author_role   = st.session_state.get("author_role", "Content Team")
                _author_avatar = st.session_state.get("author_avatar_url", "")
                _avatar_tag    = (
                    f'<img src="{_author_avatar}" alt="{_author_name}" '
                    f'width="56" height="56" style="border-radius:50%;float:left;margin-right:14px;object-fit:cover;">'
                    if _author_avatar else ""
                )
                _author_html = (
                    f'<div style="border-top:1px solid #e0e0e0;margin-top:32px;padding-top:20px;">'
                    f'{_avatar_tag}'
                    f'<strong style="font-size:15px;">{_author_name}</strong>'
                    f'<br><span style="color:#666;font-size:13px;">{_author_role}, myHQ</span>'
                    f'</div>'
                )

                # Parse tags
                tag_names = [t.strip() for t in tags_input.split(",") if t.strip()]

                # Canonical URL
                _slug = result.get("url_slug", "")
                _canonical = f"https://myhq.in/blog/{_slug}/" if _slug else ""

                wp_result = create_post(
                    site_url=_wp_url, username=_wp_user, app_password=_wp_pass,
                    title=result.get("blog_title", ""),
                    content=enriched_content,
                    slug=_slug,
                    meta_title=result.get("meta_title", ""),
                    meta_description=result.get("meta_description", ""),
                    focus_keyword=result.get("focus_keyword", ""),
                    status=wp_status_value,
                    featured_media_id=media_id,
                    featured_media_url=media_url,
                    schema_markup=result.get("schema_markup", ""),
                    author_html=_author_html,
                    category_names=[_selected_category],
                    tag_names=tag_names,
                    canonical_url=_canonical,
                )
                st.session_state["wp_publish_result"] = wp_result

                # Log to tracker
                _gc_file     = st.session_state.get("gc_file", "")
                _sheet_url   = st.session_state.get("tracking_sheet_url", "")
                if _gc_file and os.path.exists(_gc_file) and _sheet_url:
                    try:
                        ensure_headers(_gc_file, _sheet_url)
                        append_tracking_row(_gc_file, _sheet_url, {
                            "title":    result.get("blog_title", ""),
                            "slug":     result.get("url_slug", ""),
                            "category": _selected_category,
                            "post_id":  wp_result["post_id"],
                            "status":   wp_result["status"],
                            "date":     datetime.now().strftime("%Y-%m-%d"),
                            "edit_url": wp_result.get("edit_url", ""),
                            "live_url": wp_result.get("post_url", ""),
                        })
                    except Exception as te:
                        st.warning(f"Tracker update failed: {te}")

            except RuntimeError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Unexpected publishing error: {e}")

    wp_result = st.session_state.get("wp_publish_result")
    if wp_result:
        st.success(f"Published as **{wp_result['status']}** — Post ID: {wp_result['post_id']}")
        link_col1, link_col2 = st.columns(2)
        with link_col1:
            if wp_result.get("post_url"):
                st.markdown(f"[View Post]({wp_result['post_url']})")
        with link_col2:
            if wp_result.get("edit_url"):
                st.markdown(f"[Edit in WP Admin]({wp_result['edit_url']})")
        if wp_result.get("meta_warning"):
            st.warning(wp_result["meta_warning"])
