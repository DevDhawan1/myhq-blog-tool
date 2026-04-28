import requests

AHREFS_API_BASE = "https://api.ahrefs.com/v3"


def get_keyword_ideas(api_key: str, topic: str, country: str = "in", limit: int = 20) -> dict:
    """
    Query Ahrefs matching-terms endpoint for a seed topic.
    Returns primary keyword (highest TP with KD ≤ 30) + up to 6 secondaries.
    """
    url = f"{AHREFS_API_BASE}/keywords-explorer/matching-terms"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "select": "keyword,volume,difficulty,traffic_potential",
        "keywords": topic,
        "country": country,
        "limit": limit,
        "order_by": "traffic_potential:desc",
        "output": "json",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    keywords = resp.json().get("keywords", [])

    if not keywords:
        return {"primary": None, "secondaries": [], "all_keywords": []}

    primary = None
    secondaries = []

    for kw in keywords:
        kd = kw.get("difficulty") or 100
        if primary is None and kd <= 30:
            primary = kw
        elif len(secondaries) < 6 and kw.get("keyword") != (primary or {}).get("keyword"):
            secondaries.append(kw)

    if primary is None and keywords:
        primary = keywords[0]
        secondaries = keywords[1:7]

    return {"primary": primary, "secondaries": secondaries, "all_keywords": keywords}


def format_keyword_data_for_prompt(kw_data: dict) -> str:
    if not kw_data or not kw_data.get("primary"):
        return ""

    p = kw_data["primary"]
    lines = [
        "KEYWORD RESEARCH (Ahrefs data — use these exactly)",
        f"Primary keyword : {p.get('keyword')}  |  Vol: {p.get('volume', '—')}  |  KD: {p.get('difficulty', '—')}  |  TP: {p.get('traffic_potential', '—')}",
        "Secondary keywords:",
    ]
    for s in kw_data.get("secondaries", []):
        lines.append(
            f"  - {s.get('keyword')}  |  Vol: {s.get('volume', '—')}  |  KD: {s.get('difficulty', '—')}"
        )
    lines.append(
        "\nSet focus_keyword to the primary keyword above. Use secondary keywords as subsidiary_keywords."
    )
    return "\n".join(lines)
