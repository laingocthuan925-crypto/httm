"""Paper Reader: tải PDF open-access -> chunk -> embedding (chạy nền)."""
from fastapi import APIRouter, BackgroundTasks

from app.db import get_pool
from app.services.ingest import ingest_project_papers
from app.services.store import save_artifact

router = APIRouter(prefix="/reader", tags=["reader"])


async def run_ingest(pid: int) -> dict:
    res = await ingest_project_papers(pid)
    await save_artifact(pid, "ingest", res)
    return res


@router.post("/{project_id}/ingest")
async def ingest(project_id: int, bg: BackgroundTasks):
    bg.add_task(run_ingest, project_id)
    return {"status": "started"}


@router.get("/{project_id}/status")
async def status(project_id: int):
    async with get_pool().acquire() as c:
        rows = await c.fetch(
            "SELECT pp.paper_id, count(c.id) AS chunks FROM project_papers pp "
            "LEFT JOIN paper_chunks c ON c.paper_id=pp.paper_id "
            "WHERE pp.project_id=$1 AND pp.screen_status='included' GROUP BY pp.paper_id", project_id)
    return {"papers": len(rows), "with_fulltext": sum(1 for r in rows if r["chunks"] > 0)}
