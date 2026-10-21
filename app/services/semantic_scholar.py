import os
import httpx

URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "paperId,title,abstract,year,externalIds,openAccessPdf,citationCount,authors,venue"


async def search_semantic_scholar(query: str, limit: int = 20) -> list[dict]:
    key = os.environ.get("S2_API_KEY")
    headers = {"x-api-key": key} if key else {}
    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as c:
            r = await c.get(URL, params={"query": query, "limit": limit, "fields": FIELDS})
            if r.status_code == 429:
                return []                # bị rate-limit: bỏ qua, OpenAlex vẫn chạy
            r.raise_for_status()
            data = r.json().get("data", [])
    except httpx.HTTPError:
        return []
    out = []
    for p in data:
        if not p.get("title"):
            continue
        doi = (p.get("externalIds") or {}).get("DOI")
        out.append({
            "source": "semantic_scholar",
            "id": "S2_" + p["paperId"],
            "title": p["title"],
            "abstract": p.get("abstract"),
            "year": p.get("year"),
            "doi": doi.lower() if doi else None,
            "oa_url": (p.get("openAccessPdf") or {}).get("url"),
            "authors": [a["name"] for a in p.get("authors", []) if a.get("name")],
            "venue": p.get("venue") or None,
            "citation_count": p.get("citationCount"),
        })
    return out


def _key(p: dict) -> str:
    return p.get("doi") or "".join(ch for ch in (p.get("title") or "").lower() if ch.isalnum())


def merge_dedupe(*lists: list[dict]) -> list[dict]:
    """Gộp nhiều nguồn; trùng DOI/title thì giữ bản đầu (ưu tiên OpenAlex), bổ sung field thiếu."""
    merged: dict[str, dict] = {}
    for lst in lists:
        for p in lst:
            k = _key(p)
            if not k:
                continue
            if k in merged:
                for f in ("abstract", "oa_url", "doi", "year", "venue"):
                    if not merged[k].get(f) and p.get(f):
                        merged[k][f] = p[f]
                if not merged[k].get("authors") and p.get("authors"):
                    merged[k]["authors"] = p["authors"]
            else:
                merged[k] = dict(p)
    return list(merged.values())
