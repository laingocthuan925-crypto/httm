import os
import httpx

BASE = "https://api.openalex.org/works"


def short_id(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip() or None


def rebuild_abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos)) or None


async def search_openalex(query: str, limit: int = 30, from_year: int | None = None) -> list[dict]:
    flt = "has_abstract:true,type:article"
    if from_year:
        flt += f",from_publication_date:{from_year}-01-01"
    params = {"search": query, "per-page": min(limit, 100), "filter": flt}
    if os.environ.get("OPENALEX_MAILTO"):
        params["mailto"] = os.environ["OPENALEX_MAILTO"]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(BASE, params=params)
        r.raise_for_status()
        results = r.json().get("results", [])
    out = []
    for w in results:
        loc = w.get("best_oa_location") or {}
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        out.append({
            "source": "openalex",
            "id": short_id(w["id"]),
            "title": w.get("title") or w.get("display_name"),
            "abstract": rebuild_abstract(w.get("abstract_inverted_index")),
            "year": w.get("publication_year"),
            "doi": norm_doi(w.get("doi")),
            "oa_url": loc.get("pdf_url") or (w.get("open_access") or {}).get("oa_url"),
            "authors": [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
            "venue": venue,
            "citation_count": w.get("cited_by_count"),
        })
    return [p for p in out if p["title"]]
