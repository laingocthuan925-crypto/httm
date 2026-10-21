"""Analyst: mỗi paper -> PaperAnalysis có quote nguyên văn đã kiểm chứng."""
import asyncio
import json
from fastapi import APIRouter

from app.db import get_pool
from app.pipeline_models import PaperAnalysis, ExtractedClaim
from app.services.llm import generate_structured
from app.services.quotes import quote_supported
from app.services.retrieval import get_evidence_items
from app.services.store import get_project
from app.services import prompts as P

router = APIRouter(prefix="/analyze", tags=["analysis"])


async def analyze_one(pid: int, paper: dict, focus: str) -> dict:
    queries = [focus, "research methodology sample data collection analysis",
               "results findings effects limitations conclusions"]
    items, source = await get_evidence_items(paper["id"], paper["abstract"], queries)
    if not items:
        return {"paper_id": paper["id"], "status": "no_text"}
    context = "\n\n".join(f"[{i['ref']}] {i['text']}" for i in items)
    res: PaperAnalysis = await generate_structured(
        P.analysis_prompt(paper, context, source, focus), PaperAnalysis, system=P.ANALYST_SYSTEM, temperature=0.1)

    src = {i["ref"]: i["text"] for i in items}
    kept, dropped = [], 0
    for c in res.key_findings:
        good = [e for e in c.evidence if e.chunk_ref in src and quote_supported(e.quote, src[e.chunk_ref])]
        if good:
            kept.append(ExtractedClaim(statement=c.statement, claim_type=c.claim_type, evidence=good))
        else:
            dropped += 1                         # claim không có quote thật -> loại (chống bịa)
    res.key_findings = kept
    data = res.model_dump()
    data["_dropped_claims"] = dropped
    async with get_pool().acquire() as c:
        await c.execute(
            "INSERT INTO paper_analyses(project_id,paper_id,analysis,source) VALUES($1,$2,$3::jsonb,$4) "
            "ON CONFLICT (project_id,paper_id) DO UPDATE SET analysis=EXCLUDED.analysis, source=EXCLUDED.source, created_at=now()",
            pid, paper["id"], json.dumps(data, ensure_ascii=False), source)
    return {"paper_id": paper["id"], "status": "ok", "source": source, "kept": len(kept), "dropped": dropped}


async def run_analysis(pid: int, limit: int | None = None, concurrency: int = 3, force: bool = False) -> dict:
    proj = await get_project(pid)
    focus = proj["topic"] + "; " + "; ".join(proj["plan"].get("research_questions", [])[:2])
    async with get_pool().acquire() as c:
        rows = await c.fetch(
            "SELECT p.id, p.title, p.year, p.abstract FROM project_papers pp JOIN papers p ON p.id=pp.paper_id "
            "LEFT JOIN paper_analyses a ON a.paper_id=p.id AND a.project_id=pp.project_id "
            "WHERE pp.project_id=$1 AND pp.screen_status='included' AND ($2 OR a.paper_id IS NULL)", pid, force)
    papers = [dict(r) for r in rows][: limit or None]
    sem = asyncio.Semaphore(concurrency)

    async def guarded(p):
        async with sem:
            try:
                return await analyze_one(pid, p, focus)
            except Exception as e:
                return {"paper_id": p["id"], "status": f"error:{type(e).__name__}"}

    results = await asyncio.gather(*(guarded(p) for p in papers))
    return {"analyzed": sum(r["status"] == "ok" for r in results), "results": results}


@router.post("/{project_id}")
async def analyze(project_id: int, limit: int | None = None, force: bool = False):
    return await run_analysis(project_id, limit=limit, force=force)


@router.get("/{project_id}")
async def get_analyses(project_id: int):
    async with get_pool().acquire() as c:
        rows = await c.fetch("SELECT paper_id, source, analysis FROM paper_analyses WHERE project_id=$1", project_id)
    return [{"paper_id": r["paper_id"], "source": r["source"],
             "analysis": json.loads(r["analysis"]) if isinstance(r["analysis"], str) else r["analysis"]} for r in rows]
