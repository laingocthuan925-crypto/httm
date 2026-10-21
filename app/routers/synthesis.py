"""Synthesis + Gap Detector. Gap phải được người dùng xác nhận (confirmed) trước khi sinh RQ."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.pipeline_models import Synthesis
from app.services.evidence import build_evidence_index
from app.services.citations import inline_cite
from app.services.llm import generate_structured
from app.services.store import get_project, save_artifact, load_artifact
from app.services import prompts as P

router = APIRouter(prefix="/synthesize", tags=["synthesis"])


def digest(index: dict) -> str:
    lines = []
    for p in index.values():
        if not p["findings"]:
            continue
        lines.append(f"[{p['id']}] {inline_cite(p)} | design: {p['method'] or 'n/r'} | sample: {p['sample'] or 'n/r'} | base: {p['source']}")
        lines += [f"    - {c['statement']}" for c in p["findings"]]
    return "\n".join(lines)


async def run_synthesis(pid: int) -> dict:
    proj = await get_project(pid)
    index = await build_evidence_index(pid)
    dg = digest(index)
    if not dg:
        raise HTTPException(400, "Chưa có paper nào được phân tích. Chạy /analyze trước.")
    res: Synthesis = await generate_structured(P.synthesis_prompt(proj["plan"], dg), Synthesis,
                                               system=P.SYNTH_SYSTEM, temperature=0.2)
    ok = set(index)
    clean = lambda ids: [i for i in ids if i in ok]      # bỏ id LLM bịa
    data = res.model_dump()
    for t in data["themes"]:
        t["paper_ids"] = clean(t["paper_ids"])
    for c in data["contradictions"]:
        c["paper_ids"] = clean(c["paper_ids"])
    for n, g in enumerate(data["gaps"], 1):
        g["gap_id"], g["confirmed"], g["paper_ids"] = f"G{n}", False, clean(g["paper_ids"])
    await save_artifact(pid, "synthesis", data)
    return data


class ConfirmBody(BaseModel):
    gap_ids: list[str]


@router.post("/{project_id}")
async def synthesize(project_id: int):
    return await run_synthesis(project_id)


@router.get("/{project_id}")
async def get_synthesis(project_id: int):
    d = await load_artifact(project_id, "synthesis")
    if d is None:
        raise HTTPException(404, "Chưa có synthesis.")
    return d


@router.post("/{project_id}/confirm")
async def confirm_gaps(project_id: int, body: ConfirmBody):
    d = await load_artifact(project_id, "synthesis")
    if d is None:
        raise HTTPException(404, "Chưa có synthesis.")
    for g in d["gaps"]:
        g["confirmed"] = g["gap_id"] in body.gap_ids
    await save_artifact(project_id, "synthesis", d)
    return {"confirmed": [g["gap_id"] for g in d["gaps"] if g["confirmed"]]}
