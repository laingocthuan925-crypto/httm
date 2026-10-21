"""Literature Search (OpenAlex + Semantic Scholar) và Screening (lọc theo abstract)."""
import asyncio
import json
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_pool
from app.pipeline_models import ScreenBatch
from app.services.llm import generate_structured
from app.services.openalex import search_openalex
from app.services.semantic_scholar import search_semantic_scholar, merge_dedupe
from app.services.store import get_project
from app.services import prompts as P

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    max_per_source: int = 30
    from_year: Optional[int] = None


def build_queries(plan: dict) -> list[str]:
    kws = plan.get("keywords", [])
    syn = {s["keyword"]: s["synonyms"] for s in plan.get("synonyms", [])}
    qs = []
    if kws:
        qs.append(" ".join(kws[:3]))
        qs.append(f"{kws[0]} {(syn.get(kws[0]) or kws[1:2] or [''])[0]}".strip())
    if len(kws) > 3:
        qs.append(" ".join(kws[1:4]))
    return [q for q in dict.fromkeys(qs) if q]


async def run_search(pid: int, max_per_source: int = 30, from_year: int | None = None) -> dict:
    proj = await get_project(pid)
    queries = build_queries(proj["plan"])
    tasks = []
    for q in queries:
        tasks.append(search_openalex(q, max_per_source, from_year))
        tasks.append(search_semantic_scholar(q, max_per_source))
    results = await asyncio.gather(*tasks, return_exceptions=True)

    per_run, oa, s2 = [], [], []
    for i, res in enumerate(results):
        q, src = queries[i // 2], ("openalex" if i % 2 == 0 else "semantic_scholar")
        ok = [] if isinstance(res, Exception) else res
        per_run.append((q, src, len(ok)))
        (oa if src == "openalex" else s2).extend(ok)
    merged = merge_dedupe(oa, s2)   # OpenAlex ưu tiên

    async with get_pool().acquire() as conn:
        async with conn.transaction():
            for q, src, n in per_run:
                await conn.execute("INSERT INTO search_runs(project_id, source, query, n_results) VALUES($1,$2,$3,$4)", pid, src, q, n)
            for p in merged:
                await conn.execute(
                    "INSERT INTO papers(id,title,abstract,year,doi,oa_url,source,authors,venue,citation_count) "
                    "VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10) ON CONFLICT (id) DO UPDATE SET "
                    "abstract=COALESCE(papers.abstract,EXCLUDED.abstract), oa_url=COALESCE(papers.oa_url,EXCLUDED.oa_url)",
                    p["id"], p["title"], p.get("abstract"), p.get("year"), p.get("doi"), p.get("oa_url"),
                    p["source"], json.dumps(p.get("authors") or []), p.get("venue"), p.get("citation_count"))
                await conn.execute("INSERT INTO project_papers(project_id,paper_id) VALUES($1,$2) ON CONFLICT DO NOTHING", pid, p["id"])
    return {"queries": queries, "found_total": len(oa) + len(s2), "unique": len(merged), "runs": per_run}


async def run_screening(pid: int, batch: int = 15, max_include: int | None = None) -> dict:
    proj = await get_project(pid)
    async with get_pool().acquire() as c:
        rows = await c.fetch(
            "SELECT p.id, p.title, p.year, p.abstract FROM project_papers pp JOIN papers p ON p.id=pp.paper_id "
            "WHERE pp.project_id=$1 AND pp.screen_status='candidate'", pid)
    cands = [dict(r) for r in rows]
    no_abs = [p for p in cands if not p["abstract"]]
    with_abs = [p for p in cands if p["abstract"]]
    decisions = {p["id"]: (False, "Không có abstract để đánh giá") for p in no_abs}
    for i in range(0, len(with_abs), batch):
        chunk = with_abs[i:i + batch]
        res: ScreenBatch = await generate_structured(P.screening_prompt(proj["plan"], chunk), ScreenBatch, temperature=0.0)
        valid = {p["id"] for p in chunk}
        for d in res.decisions:
            if d.paper_id in valid:
                decisions[d.paper_id] = (d.include, d.reason)
    if max_include:
        inc = [pid_ for pid_, (ok, _) in decisions.items() if ok]
        for extra in inc[max_include:]:
            decisions[extra] = (False, "Vượt giới hạn số paper")
    async with get_pool().acquire() as c:
        async with conn_tx(c):
            for pid_, (ok, reason) in decisions.items():
                await c.execute("UPDATE project_papers SET screen_status=$3, screen_reason=$4 WHERE project_id=$1 AND paper_id=$2",
                                pid, pid_, "included" if ok else "excluded", reason)
    inc = sum(1 for ok, _ in decisions.values() if ok)
    return {"screened": len(decisions), "included": inc, "excluded": len(decisions) - inc}


def conn_tx(c):
    return c.transaction()


@router.post("/{project_id}")
async def search(project_id: int, body: SearchRequest = SearchRequest()):
    return await run_search(project_id, body.max_per_source, body.from_year)


@router.post("/{project_id}/screen")
async def screen(project_id: int, max_include: Optional[int] = None):
    return await run_screening(project_id, max_include=max_include)


@router.get("/{project_id}/papers")
async def list_papers(project_id: int, status: Optional[str] = None):
    async with get_pool().acquire() as c:
        rows = await c.fetch(
            "SELECT p.id, p.title, p.year, p.doi, p.oa_url IS NOT NULL AS has_pdf, pp.screen_status, pp.screen_reason "
            "FROM project_papers pp JOIN papers p ON p.id=pp.paper_id WHERE pp.project_id=$1 "
            "AND ($2::text IS NULL OR pp.screen_status=$2) ORDER BY p.year DESC NULLS LAST", project_id, status)
    return [dict(r) for r in rows]
