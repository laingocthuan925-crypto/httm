import json
from fastapi import HTTPException
from app.db import get_pool


async def save_artifact(pid: int, kind: str, data) -> None:
    async with get_pool().acquire() as c:
        await c.execute(
            "INSERT INTO project_artifacts(project_id, kind, data) VALUES($1,$2,$3::jsonb) "
            "ON CONFLICT (project_id, kind) DO UPDATE SET data=EXCLUDED.data, updated_at=now()",
            pid, kind, json.dumps(data, ensure_ascii=False))


async def load_artifact(pid: int, kind: str, default=None):
    async with get_pool().acquire() as c:
        row = await c.fetchrow("SELECT data FROM project_artifacts WHERE project_id=$1 AND kind=$2", pid, kind)
    if row is None:
        return default
    d = row["data"]
    return json.loads(d) if isinstance(d, str) else d


async def get_project(pid: int) -> dict:
    async with get_pool().acquire() as c:
        row = await c.fetchrow("SELECT id, topic, research_plan FROM research_projects WHERE id=$1", pid)
    if row is None:
        raise HTTPException(404, "Không tìm thấy project.")
    plan = row["research_plan"]
    return {"id": row["id"], "topic": row["topic"], "plan": json.loads(plan) if isinstance(plan, str) else plan}


DEFAULT_CONFIG = {"paper_type": "systematic_review", "language": "en", "venue": None, "target_words": 6000}


async def get_config(pid: int) -> dict:
    return {**DEFAULT_CONFIG, **(await load_artifact(pid, "config", {}) or {})}
