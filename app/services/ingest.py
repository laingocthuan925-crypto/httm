"""Pipeline: papers.oa_url -> PDF -> chunks -> embeddings -> paper_chunks (asyncpg)."""
import asyncio
import logging
import httpx

from app.db import get_pool
from app.services.pdf_fetcher import fetch_pdf, HEADERS
from app.services.pdf_chunker import extract_pages, chunk_pages
from app.services.embeddings import embed_documents

log = logging.getLogger(__name__)


async def ingest_paper(paper: dict, client: httpx.AsyncClient) -> str:
    pdf = await fetch_pdf(paper["oa_url"], client)
    if not pdf:
        return "no_pdf"
    chunks = chunk_pages(extract_pages(pdf))
    if not chunks:
        return "no_text"                     # PDF scan / rỗng
    vecs = await asyncio.to_thread(embed_documents, [c["text"] for c in chunks])
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM paper_chunks WHERE paper_id=$1", paper["id"])
            await conn.executemany(
                "INSERT INTO paper_chunks (paper_id, chunk_index, page, chunk_text, embedding) "
                "VALUES ($1,$2,$3,$4,$5)",
                [(paper["id"], i, c["page"], c["text"], v)
                 for i, (c, v) in enumerate(zip(chunks, vecs))],
            )
    return "ok"


async def ingest_project_papers(project_id: int) -> dict[str, str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT p.id, p.oa_url FROM papers p JOIN project_papers pp ON pp.paper_id=p.id "
            "WHERE pp.project_id=$1 AND pp.screen_status='included' AND p.oa_url IS NOT NULL", project_id)
    result: dict[str, str] = {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS) as client:
        for r in rows:
            try:
                result[r["id"]] = await ingest_paper(dict(r), client)
            except Exception as e:           # 1 paper lỗi không làm hỏng cả lô
                log.warning("ingest %s lỗi: %s", r["id"], e)
                result[r["id"]] = f"error:{type(e).__name__}"
    return result
