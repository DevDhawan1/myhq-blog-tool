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


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="myHQ Blog Drafting Tool",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.kw-chip { display:inline-block; background:#e8f4fd; color:#1a73e8;
           border-radius:16px; padding:3px 12px; margin:3px; font-size:13px; }
.char-ok  { color:#2d8a4e; font-size:12px; }
.char-bad { color:#c0392b; font-size:12px; }
</style>
""", unsafe_allow_html=True)



# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    try:
        st.image("https://play-lh.googleusercontent.com/IYnsXC7SsNBIPKq1XMMfiWdPrdbd9IlTHl1cDaBHAITTVOVIyUyUAUm6vsN7IDRtgEw",
                 width=100)
    except Exception:
        st.markdown("### myHQ")

    st.title("Settings")

    # ── API Keys section ──────────────────────────────────────────────────────
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
            help="Free at console.groq.com — no card needed, 14,400 req/day",
        )
        st.session_state["groq_api_key"] = groq_key
        if groq_key:
            os.environ["GROQ_API_KEY"] = groq_key
        api_key = groq_key  # used for the "no key" guard below
    else:
        api_key = st.text_input(
            "Gemini API Key  *(required)*",
            value=st.session_state.get("gemini_api_key", os.environ.get("GEMINI_API_KEY", "")),
            type="password",
            help="Free from aistudio.google.com → Sign in → Get API Key",
        )
        st.session_state["gemini_api_key"] = api_key
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key

        gemini_model = st.selectbox(
            "Gemini Model",
            options=["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"],
            index=0,
            help="gemini-2.0-flash: 1500 req/day free  |  gemini-2.5-flash: 20 req/day free",
        )
        st.session_state["gemini_model"] = gemini_model

    free_image_api_key = st.text_input(
        "Image API Key  *(primary)*",
        value=st.session_state.get("free_image_api_key", os.environ.get("FREE_IMAGE_API_KEY", "")),
        type="password",
        help="Bearer token for the free-image-generator-api Cloudflare Worker.",
    )
    st.session_state["free_image_api_key"] = free_image_api_key
    if free_image_api_key:
        os.environ["FREE_IMAGE_API_KEY"] = free_image_api_key

    unsplash_key = st.text_input(
        "Unsplash Key  *(last-resort fallback)*",
        value=st.session_state.get("unsplash_key", os.environ.get("UNSPLASH_ACCESS_KEY", "")),
        type="password",
        help="Free from unsplash.com/developers — used only if both image APIs fail.",
    )
    st.session_state["unsplash_key"] = unsplash_key
    if unsplash_key:
        os.environ["UNSPLASH_ACCESS_KEY"] = unsplash_key

    st.divider()

    # ── WordPress credentials section ─────────────────────────────────────────
    st.subheader("WordPress")
    st.caption("Optional — required only to publish directly to WP.")

    wp_site_url = st.text_input(
        "WP Site URL",
        value=st.session_state.get("wp_site_url", os.environ.get("WP_SITE_URL", "")),
        placeholder="https://myhqblog.in",
        help="Your WordPress site root URL (no trailing slash).",
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
        help="Generate at WP Admin → Users → Profile → Application Passwords.",
    )
    st.session_state["wp_app_password"] = wp_app_password
    if wp_app_password:
        os.environ["WP_APP_PASSWORD"] = wp_app_password

    st.divider()

    # ── Author defaults ───────────────────────────────────────────────────────
    st.subheader("Author")
    st.caption("Appended to every published post.")

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

    # ── Blog context section ──────────────────────────────────────────────────
    st.subheader("Blog Context")

    context = load_context()
    if context:
        scraped_date = context.get("scraped_at", "")[:10]
        st.success(f"✅ {context['total_blogs']} blogs indexed")
        st.caption(f"💰 {len(context.get('money_pages', []))} money pages detected")
        st.caption(f"Last refreshed: {scraped_date}")
    else:
        st.warning("Context not loaded. Click Refresh below.")

    if st.button("🔄 Refresh Context", use_container_width=True,
                 help="Re-scrapes all of myhqblog.in (~3–5 min for 200+ blogs)"):
        prog = st.progress(0)
        status = st.empty()

        def _cb(pct, msg):
            prog.progress(pct)
            status.caption(msg)

        with st.spinner("Crawling myhqblog.in…"):
            try:
                context = build_context(progress_callback=_cb)
                prog.progress(1.0)
                status.caption("Done!")
                st.success(
                    f"Indexed {context['total_blogs']} blogs, "
                    f"{len(context['money_pages'])} money pages"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Scrape failed: {e}")

    if context and st.checkbox("Show detected money pages"):
        for mp in context.get("money_pages", [])[:25]:
            anchors = ", ".join(mp.get("anchor_texts", [])[:2])
            st.caption(f"• {mp['url']}  ({mp['link_count']}×)  {anchors}")


# ── Main ──────────────────────────────────────────────────────────────────────
st.title("✍️ myHQ Blog Drafting Tool")
st.caption("SEO-optimised blog drafts — Gemini AI · Pollinations.ai · auto money-page detection")

if not context:
    st.info("👈 Click **Refresh Context** in the sidebar first to index your blog data.")
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
            "Word Count *", min_value=300, max_value=5000, value=1200, step=100
        )

    col3, col4, col5 = st.columns(3)
    with col3:
        keyword_density = st.slider(
            "Keyword Density (%)", min_value=0.5, max_value=3.0, value=1.5, step=0.1
        )
    with col4:
        n_internal = st.number_input("Internal Blog Links", min_value=0, max_value=10, value=3)
    with col5:
        n_money = st.number_input("Money Page Links", min_value=0, max_value=10, value=2)

    blog_category = st.radio(
        "Blog Category *",
        options=["Office Space", "Virtual Office"],
        horizontal=True,
    )

    with st.expander("Override Money Pages for this blog (optional)"):
        st.caption(
            "Paste specific money page URLs (one per line) to use instead of auto-detected ones."
        )
        override_raw = st.text_area(
            "Custom money page URLs",
            height=110,
            placeholder="https://myhq.in/coworking-spaces/bangalore\nhttps://myhq.in/virtual-office/delhi",
        )

    submitted = st.form_submit_button(
        "Generate Blog Draft", type="primary", use_container_width=True
    )

# ── Trigger generation ────────────────────────────────────────────────────────
if submitted:
    _provider = st.session_state.get("llm_provider", "Groq (free, 14,400/day)")
    if not api_key:
        _key_name = "Groq" if "Groq" in _provider else "Gemini"
        st.error(f"Enter your {_key_name} API key in the sidebar.")
        st.stop()
    if not topic.strip():
        st.error("Please enter a blog topic.")
        st.stop()

    override_money = None
    if override_raw.strip():
        urls = [u.strip() for u in override_raw.strip().splitlines() if u.strip()]
        override_money = [{"url": u, "anchor_texts": [], "link_count": 0} for u in urls]

    _spinner_msg = "Asking Groq (Llama 3.3 70B) to write your blog…" if "Groq" in _provider else "Asking Gemini to write your blog… (auto-retries on rate limit)"
    with st.spinner(_spinner_msg):
        try:
            if "Groq" in _provider:
                client = setup_groq(api_key)
                result = generate_blog_groq(
                    client, topic, word_count, keyword_density,
                    n_internal, n_money, context, override_money,
                )
            else:
                model = setup_gemini(api_key, st.session_state.get("gemini_model", "gemini-2.0-flash"))
                result = generate_blog(
                    model, topic, word_count, keyword_density,
                    n_internal, n_money, context, override_money,
                )
            st.session_state["result"] = result
            st.session_state["blog_category"] = blog_category
            st.session_state["generated_at"] = datetime.now().strftime("%d %b %Y, %H:%M")
            st.session_state["seo_score"] = seo_quality_score(
                result, n_internal, n_money, keyword_density, word_count,
            )
            st.session_state["img_bytes"] = None   # reset image cache on new generation
            st.session_state["img_url"] = None
            st.session_state["img_credit"] = None
            st.session_state["wp_publish_result"] = None  # reset publish state on new generation
            st.session_state["docx_auto_saved"] = False   # trigger auto-save on next render
            st.session_state["docx_save_path"] = None
        except Exception as e:
            st.error(f"Generation error: {e}")
            st.stop()

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

# ── Feature image ──────────────────────────────────────────────────────────────
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
            credit = "Generated with free-image-generator-api" if _api_key else "Generated with Pollinations.ai · Flux Realism"
            st.session_state["img_credit"] = credit
        except Exception as e:
            st.warning(f"Image generation failed: {e}. Falling back to Unsplash.")
            st.session_state["img_bytes"] = b""

    if not st.session_state.get("img_bytes"):
        if unsplash_key:
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
        else:
            st.session_state["img_bytes"]  = b""
            st.session_state["img_url"]    = ""
            st.session_state["img_credit"] = ""

img_bytes  = st.session_state.get("img_bytes", b"")
img_url    = st.session_state.get("img_url", "")
img_credit = st.session_state.get("img_credit", "")

if img_bytes:
    st.image(img_bytes, use_container_width=True)
    _api_key_check = os.environ.get("FREE_IMAGE_API_KEY", "")
    _source_label = "Source: free-image-generator-api" if _api_key_check else "Source: Pollinations.ai (fallback — add FREE_IMAGE_API_KEY to .env)"
    st.caption(_source_label + (f"  |  {img_credit}" if img_credit else ""))
elif img_url:
    st.image(img_url, use_container_width=True)
    if img_credit:
        st.caption(img_credit)
else:
    st.info("Image generation failed. Add an Unsplash key in the sidebar as a fallback.")

with st.expander("Image details"):
    st.caption(f"Prompt: {blog_title}")

# ── SEO metadata ───────────────────────────────────────────────────────────────
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
        f'<span class="kw-chip">{kw}</span>' for kw in result.get("subsidiary_keywords", [])
    )
    st.markdown(chips, unsafe_allow_html=True)

# ── SEO Quality Score ─────────────────────────────────────────────────────────
seo_score_data = st.session_state.get("seo_score")
if seo_score_data:
    _sc = seo_score_data["score"]
    _mx = seo_score_data["max"]
    if _sc >= 10:
        _score_color = "#2d8a4e"   # green
        _score_label = "Excellent"
    elif _sc >= 7:
        _score_color = "#d4a017"   # yellow
        _score_label = "Good"
    else:
        _score_color = "#c0392b"   # red
        _score_label = "Needs Work"

    with st.expander(f"SEO Score: {_sc}/{_mx} — {_score_label}"):
        for check in seo_score_data["checks"]:
            _icon = "✅" if check["passed"] else "⚠️"
            st.markdown(f"{_icon} **{check['name']}** — {check['detail']}")

# ── Build enriched content (TL;DR injected after first paragraph) ──────────────
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
    # Inject just before the first <h2> — after intro paragraphs, before content sections
    _insert_at = _raw_content.find("<h2")
    if _insert_at != -1:
        enriched_content = (
            _raw_content[: _insert_at]
            + _tldr_html + "\n"
            + _raw_content[_insert_at :]
        )
    else:
        enriched_content = _tldr_html + "\n" + _raw_content
else:
    enriched_content = _raw_content

schema_str = result.get("schema_markup", "")
if schema_str:
    with st.expander("JSON-LD Schema Markup"):
        try:
            import json as _json
            st.code(_json.dumps(_json.loads(schema_str), indent=2), language="json")
        except Exception:
            st.code(schema_str, language="json")

# ── Blog content ───────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"## {result.get('blog_title', '')}")

tab_preview, tab_html = st.tabs(["Rendered Preview", "Raw HTML"])
with tab_preview:
    st.markdown(enriched_content, unsafe_allow_html=True)
with tab_html:
    st.text_area(
        "", enriched_content, height=450,
        key="raw_html_box", label_visibility="collapsed",
    )

# ── Downloads ──────────────────────────────────────────────────────────────────
st.divider()
st.markdown("#### Download Draft")

slug = result.get("url_slug", "blog-draft")
full_draft = {"generated_at": st.session_state.get("generated_at", ""), **result}

if st.session_state.get("docx_save_path"):
    st.info(f"💾 Auto-saved: `{st.session_state['docx_save_path']}`")

dl1, dl2, dl3 = st.columns(3)

with dl1:
    # Word document
    with st.spinner("Building .docx…"):
        try:
            docx_bytes = build_docx(result, img_bytes if img_bytes else None)

            # Auto-save once per generation to the user's Downloads folder
            if not st.session_state.get("docx_auto_saved"):
                _dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(_dl_dir, exist_ok=True)
                _save_path = os.path.join(_dl_dir, f"{slug}.docx")
                with open(_save_path, "wb") as _fh:
                    _fh.write(docx_bytes)
                st.session_state["docx_auto_saved"] = True
                st.session_state["docx_save_path"] = _save_path

            st.download_button(
                "⬇️ Word Document (.docx)",
                data=docx_bytes,
                file_name=f"{slug}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as e:
            st.warning(f"DOCX build failed: {e}")

with dl2:
    st.download_button(
        "⬇️ JSON (all fields)",
        data=json.dumps(full_draft, indent=2, ensure_ascii=False),
        file_name=f"{slug}.json",
        mime="application/json",
        use_container_width=True,
    )

with dl3:
    txt = (
        f"META TITLE: {result.get('meta_title', '')}\n"
        f"META DESCRIPTION: {result.get('meta_description', '')}\n"
        f"FOCUS KEYWORD: {result.get('focus_keyword', '')}\n"
        f"SUBSIDIARY KEYWORDS: {', '.join(result.get('subsidiary_keywords', []))}\n"
        f"URL SLUG: {result.get('url_slug', '')}\n\n"
        f"TITLE: {result.get('blog_title', '')}\n\n"
        f"--- CONTENT (HTML) ---\n{result.get('content', '')}\n"
    )
    st.download_button(
        "⬇️ Plain Text (.txt)",
        data=txt,
        file_name=f"{slug}.txt",
        mime="text/plain",
        use_container_width=True,
    )

# ── Publish to WordPress ───────────────────────────────────────────────────────
st.divider()
st.markdown("#### Publish to WordPress")

_wp_url  = st.session_state.get("wp_site_url", "")
_wp_user = st.session_state.get("wp_username", "")
_wp_pass = st.session_state.get("wp_app_password", "")

if not (_wp_url and _wp_user and _wp_pass):
    st.info("Enter your WordPress credentials in the sidebar to enable direct publishing.")
else:
    wp_status_choice = st.selectbox(
        "Publish status",
        options=["Draft", "Publish Live"],
        index=0,
        help=(
            "Draft = saved to WP but not publicly visible. "
            "Publish Live = immediately live on your site."
        ),
    )
    wp_status_value = "draft" if wp_status_choice == "Draft" else "publish"

    _selected_category = st.session_state.get("blog_category", "Office Space")
    st.caption(f"Category: **{_selected_category}**")

    if st.button("🚀 Publish to WordPress", type="primary"):
        _img_bytes = st.session_state.get("img_bytes") or b""

        with st.spinner("Publishing to WordPress…"):
            try:
                # Step 1: upload featured image (non-fatal if it fails)
                media_id = 0
                media_url = ""
                if _img_bytes:
                    try:
                        _media = upload_media(
                            site_url=_wp_url,
                            username=_wp_user,
                            app_password=_wp_pass,
                            image_bytes=_img_bytes,
                            filename=f"{result.get('url_slug', 'feature-image')}.png",
                            alt_text=f"{result.get('focus_keyword', '')} – {result.get('blog_title', '')}".strip(" –"),
                        )
                        media_id = _media["id"]
                        media_url = _media["url"]
                    except Exception as img_err:
                        st.warning(
                            f"Feature image upload failed ({img_err}). "
                            "Post will be created without a featured image."
                        )

                # Step 2: build author HTML block
                _author_name = st.session_state.get("author_name", "myHQ Team")
                _author_role = st.session_state.get("author_role", "Content Team")
                _author_avatar = st.session_state.get("author_avatar_url", "")
                if _author_avatar:
                    _avatar_tag = (
                        f'<img src="{_author_avatar}" alt="{_author_name}" '
                        f'width="56" height="56" style="border-radius:50%;'
                        f'float:left;margin-right:14px;object-fit:cover;">'
                    )
                else:
                    _avatar_tag = ""
                _author_html = (
                    f'<div style="border-top:1px solid #e0e0e0;margin-top:32px;'
                    f'padding-top:20px;display:flex;align-items:center;">'
                    f'{_avatar_tag}'
                    f'<div><strong style="font-size:15px;">{_author_name}</strong>'
                    f'<br><span style="color:#666;font-size:13px;">{_author_role}, myHQ</span></div>'
                    f'</div>'
                )

                # Step 3: category from form selection
                _cat_names = [_selected_category]

                # Step 4: create the post
                wp_result = create_post(
                    site_url=_wp_url,
                    username=_wp_user,
                    app_password=_wp_pass,
                    title=result.get("blog_title", ""),
                    content=enriched_content,
                    slug=result.get("url_slug", ""),
                    meta_title=result.get("meta_title", ""),
                    meta_description=result.get("meta_description", ""),
                    focus_keyword=result.get("focus_keyword", ""),
                    status=wp_status_value,
                    featured_media_id=media_id,
                    featured_media_url=media_url,
                    schema_markup=result.get("schema_markup", ""),
                    author_html=_author_html,
                    category_names=_cat_names,
                )
                st.session_state["wp_publish_result"] = wp_result

            except RuntimeError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Unexpected error during publishing: {e}")

    # Persist result across rerenders
    wp_result = st.session_state.get("wp_publish_result")
    if wp_result:
        st.success(
            f"Published as **{wp_result['status']}** — Post ID: {wp_result['post_id']}"
        )
        link_col1, link_col2 = st.columns(2)
        with link_col1:
            if wp_result.get("post_url"):
                st.markdown(f"[View Post →]({wp_result['post_url']})")
        with link_col2:
            if wp_result.get("edit_url"):
                st.markdown(f"[Edit in WP Admin →]({wp_result['edit_url']})")
        if wp_result.get("meta_warning"):
            st.warning(wp_result["meta_warning"])
