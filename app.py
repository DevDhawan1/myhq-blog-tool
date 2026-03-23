import streamlit as st
import json
import os
from datetime import datetime

from dotenv import load_dotenv

from scraper import build_context, load_context
from generator import setup_gemini, generate_blog
from image_generator import generate_ai_image, get_unsplash_image
from docx_exporter import build_docx

# Load .env from the same folder as this script, regardless of where you run from
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "/.env"))

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

    api_key = st.text_input(
        "Gemini API Key  *(required)*",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
        help="Free from aistudio.google.com → Sign in → Get API Key",
    )
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key

    hf_token = st.text_input(
        "Hugging Face Token  *(AI image generation)*",
        value=os.getenv("HF_TOKEN", ""),
        type="password",
        help="Free from huggingface.co → Settings → Access Tokens. Uses FLUX.1-schnell.",
    )
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token

    unsplash_key = st.text_input(
        "Unsplash Key  *(fallback if no HF token)*",
        value=os.getenv("UNSPLASH_ACCESS_KEY", ""),
        type="password",
        help="Free from unsplash.com/developers — used only if HF token is not set.",
    )
    if unsplash_key:
        os.environ["UNSPLASH_ACCESS_KEY"] = unsplash_key

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
                 help="Re-scrapes all of myhqblog.in (~3–5 min for 160+ blogs)"):
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
        "🚀 Generate Blog Draft", type="primary", use_container_width=True
    )

# ── Trigger generation ────────────────────────────────────────────────────────
if submitted:
    if not api_key:
        st.error("Enter your Gemini API key in the sidebar.")
        st.stop()
    if not topic.strip():
        st.error("Please enter a blog topic.")
        st.stop()

    override_money = None
    if override_raw.strip():
        urls = [u.strip() for u in override_raw.strip().splitlines() if u.strip()]
        override_money = [{"url": u, "anchor_texts": [], "link_count": 0} for u in urls]

    with st.spinner("Asking Gemini to write your blog…"):
        try:
            model = setup_gemini(api_key)
            result = generate_blog(
                model, topic, word_count, keyword_density,
                n_internal, n_money, context, override_money,
            )
            st.session_state["result"] = result
            st.session_state["generated_at"] = datetime.now().strftime("%d %b %Y, %H:%M")
            st.session_state["img_bytes"] = None   # reset image cache on new generation
            st.session_state["img_url"] = None
            st.session_state["img_credit"] = None
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
    st.subheader("📄 Blog Draft")
with tcol:
    st.caption(f"Generated: {st.session_state.get('generated_at', '')}")

# ── Feature image ──────────────────────────────────────────────────────────────
st.markdown("#### Feature Image")
img_prompt  = result.get("image_prompt", topic)
hf_token    = os.environ.get("HF_TOKEN", "")
unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")

if st.session_state.get("img_bytes") is None:
    if hf_token:
        with st.spinner("Generating AI image with FLUX… (20–40 sec)"):
            try:
                img_bytes = generate_ai_image(img_prompt, hf_token)
                st.session_state["img_bytes"] = img_bytes
                st.session_state["img_url"]   = ""
                st.session_state["img_credit"] = ""
            except Exception as e:
                st.warning(f"FLUX generation failed: {e}. Falling back to Unsplash.")
                st.session_state["img_bytes"] = b""

    if not hf_token or not st.session_state.get("img_bytes"):
        if unsplash_key:
            with st.spinner("Fetching image from Unsplash…"):
                img_url, img_credit = get_unsplash_image(img_prompt, unsplash_key)
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
    if img_credit:
        st.caption(img_credit)
elif img_url:
    st.image(img_url, use_container_width=True)
    if img_credit:
        st.caption(img_credit)
else:
    st.info("Add a Hugging Face token (AI images) or Unsplash key (stock photos) in the sidebar.")

with st.expander("Image details"):
    st.caption(f"Prompt: {img_prompt}")

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

# ── Blog content ───────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"## {result.get('blog_title', '')}")

tab_preview, tab_html = st.tabs(["Rendered Preview", "Raw HTML"])
with tab_preview:
    st.markdown(result.get("content", ""), unsafe_allow_html=True)
with tab_html:
    st.text_area(
        "", result.get("content", ""), height=450,
        key="raw_html_box", label_visibility="collapsed",
    )

# ── Downloads ──────────────────────────────────────────────────────────────────
st.divider()
st.markdown("#### Download Draft")

slug = result.get("url_slug", "blog-draft")
full_draft = {"generated_at": st.session_state.get("generated_at", ""), **result}

dl1, dl2, dl3 = st.columns(3)

with dl1:
    # Word document
    with st.spinner("Building .docx…"):
        try:
            docx_bytes = build_docx(result, img_bytes if img_bytes else None)
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
