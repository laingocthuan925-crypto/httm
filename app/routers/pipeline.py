"""Điều phối end-to-end. Có 2 checkpoint người duyệt (gap, RQ); auto_approve=true để chạy tự động hoàn toàn."""
import logging
from typing import Optional
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.db import get_pool
from app.services.store import save_artifact, load_artifact, get_config, DEFAULT_CONFIG
from app.routers import search, reader, analysis, synthesis, rq_generator, writer, reviewer

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
log = logging.getLogger(__name__)


class ConfigBody(BaseModel):
    paper_type: str = "systematic_review"      # systematic_review | narrative_review | conceptual
    language: str = "en"
    venue: Optional[str] = None


class RunBody(BaseModel):
    auto_approve: bool = False
    max_papers: Optional[int] = 40
    from_year: Optional[int] = None
    revise_rounds: int = 2


async def _job(pid, state, step, msg=""):
    await save_artifact(pid, "job", {"state": state, "step": step, "message": msg})


async def _run(pid: int, b: RunBody):
    try:
        async with get_pool().acquire() as c:
            n_papers = await c.fetchval("SELECT count(*) FROM project_papers WHERE project_id=$1", pid)
            n_inc = await c.fetchval("SELECT count(*) FROM project_papers WHERE project_id=$1 AND screen_status='included'", pid)
        if not n_papers:
            await _job(pid, "running", "search"); await search.run_search(pid, from_year=b.from_year)
        if not n_inc:
            await _job(pid, "running", "screen"); await search.run_screening(pid, max_include=b.max_papers)
        if not await load_artifact(pid, "ingest"):
            await _job(pid, "running", "ingest"); await reader.run_ingest(pid)
        await _job(pid, "running", "analyze"); await analysis.run_analysis(pid)

        syn = await load_artifact(pid, "synthesis")
        if not syn:
            await _job(pid, "running", "synthesize"); syn = await synthesis.run_synthesis(pid)
        if not any(g["confirmed"] for g in syn["gaps"]):
            if not b.auto_approve:
                return await _job(pid, "waiting", "confirm_gaps", "POST /synthesize/{id}/confirm rồi chạy lại /pipeline/{id}/run")
            syn["gaps"] = [{**g, "confirmed": True} for g in syn["gaps"]]
            await save_artifact(pid, "synthesis", syn)

        cands = await load_artifact(pid, "rq_candidates")
        if not cands:
            await _job(pid, "running", "rq"); cands = await rq_generator.run_rq_generation(pid)
        if not await load_artifact(pid, "rq_selected"):
            if not b.auto_approve:
                return await _job(pid, "waiting", "select_rq", "POST /rq/{id}/select rồi chạy lại")
            await rq_generator.select_rq(pid, rq_generator.best_index(cands))

        cfg = await get_config(pid)
        if cfg["paper_type"] == "conceptual" and not await load_artifact(pid, "conceptual_model"):
            await _job(pid, "running", "model"); await rq_generator.run_model(pid)

        await _job(pid, "running", "outline"); await writer.run_outline(pid)
        await _job(pid, "running", "draft"); await writer.run_draft(pid)
        for r in range(b.revise_rounds + 1):
            await _job(pid, "running", f"review_{r}")
            rev = await reviewer.run_review(pid)
            if rev["summary"]["passed"] or r == b.revise_rounds:
                break
            await _job(pid, "running", f"revise_{r}"); await writer.run_revision(pid)
        await _job(pid, "done", "export", f"passed={rev['summary']['passed']}; GET /export/{{id}}?format=docx")
    except Exception as e:
        log.exception("pipeline lỗi")
        await _job(pid, "error", "?", f"{type(e).__name__}: {getattr(e, 'detail', e)}")


@router.put("/{project_id}/config")
async def set_config(project_id: int, body: ConfigBody):
    await save_artifact(project_id, "config", {**DEFAULT_CONFIG, **body.model_dump()})
    return body


@router.post("/{project_id}/run")
async def run(project_id: int, body: RunBody, bg: BackgroundTasks):
    await _job(project_id, "running", "start")
    bg.add_task(_run, project_id, body)
    return {"status": "started"}


@router.get("/{project_id}/status")
async def status(project_id: int):
    return await load_artifact(project_id, "job", {"state": "idle"})
