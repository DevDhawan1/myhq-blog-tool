import requests
from bs4 import BeautifulSoup
import re

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_url_content(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else url

        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|article|post|entry", re.I))
            or soup.find("body")
        )
        content = main.get_text(separator=" ", strip=True) if main else ""
        content = re.sub(r"\s+", " ", content)[:4000]

        return {"url": url, "title": title_text, "content": content}
    except Exception:
        return None


def build_research_kb(urls: list[str], topic: str) -> dict:
    sources = []
    for url in urls:
        data = fetch_url_content(url)
        if data:
            sources.append(data)
    return {"topic": topic, "sources": sources, "source_count": len(sources)}


def format_kb_for_prompt(kb: dict) -> str:
    if not kb or not kb.get("sources"):
        return ""
    lines = [f"RESEARCH KNOWLEDGE BASE — Topic: {kb['topic']}", ""]
    for i, src in enumerate(kb["sources"], 1):
        lines.append(f"Source {i}: {src['title']} ({src['url']})")
        lines.append(src["content"][:1500])
        lines.append("")
    return "\n".join(lines)
