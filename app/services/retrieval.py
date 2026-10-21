"""Lấy 'bằng chứng' của 1 paper: chunk full-text gần nghĩa nhất, fallback abstract."""
import asyncio
from app.db import get_pool
from app.services.embeddings import embed_query


async def get_evidence_items(paper_id: str, abstract: str | None, queries: list[str],
                             k: int = 4, max_chars: int = 14000) -> tuple[list[dict], str]:
    """Trả ([{ref, page, text}], source) — ref dạng 'C123' (id chunk) hoặc 'ABSTRACT'."""
    async with get_pool().acquire() as conn:
        has = await conn.fetchval("SELECT 1 FROM paper_chunks WHERE paper_id=$1 LIMIT 1", paper_id)
        if not has:
            return ([{"ref": "ABSTRACT", "page": None, "text": abstract}] if abstract else []), "abstract"
        picked = {}
        for q in queries:
            qv = await asyncio.to_thread(embed_query, q)
            rows = await conn.fetch(
                "SELECT id, chunk_index, page, chunk_text FROM paper_chunks WHERE paper_id=$1 "
                "ORDER BY embedding <=> $2 LIMIT $3", paper_id, qv, k)
            for r in rows:
                picked[r["id"]] = r
    items, total = [], 0
    for r in sorted(picked.values(), key=lambda r: r["chunk_index"]):
        if total + len(r["chunk_text"]) > max_chars:
            break
        items.append({"ref": f"C{r['id']}", "page": r["page"], "text": r["chunk_text"]})
        total += len(r["chunk_text"])
    return items, "full_text"


async def closest_papers(project_id: int, text: str, k: int = 5) -> list[str]:
    """Paper trong project có chunk gần nghĩa nhất với `text` (dùng cho novelty check)."""
    qv = await asyncio.to_thread(embed_query, text)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT c.paper_id, min(c.embedding <=> $2) AS d FROM paper_chunks c "
            "JOIN project_papers pp ON pp.paper_id=c.paper_id AND pp.project_id=$1 "
            "AND pp.screen_status='included' GROUP BY c.paper_id ORDER BY d LIMIT $3", project_id, qv, k)
    return [r["paper_id"] for r in rows]
