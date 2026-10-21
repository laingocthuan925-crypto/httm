"""Research Question Generator: gap đã confirm -> RQ (feasibility + novelty), + Hypothesis/ConceptualModel."""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.pipeline_models import RQDrafts, NoveltyBatch, ConceptualModel
from app.services.evidence import build_evidence_index
from app.services.llm import generate_structured
from app.services.retrieval import closest_papers
from app.services.store import get_project, save_artifact, load_artifact, get_config
from app.services.citations import inline_cite
from app.services import prompts as P
from app.routers.synthesis import digest

router = APIRouter(prefix="/rq", tags=["rq"])


async def run_rq_generation(pid: int) -> list[dict]:
    proj = await get_project(pid)
    syn = await load_artifact(pid, "synthesis")
    if not syn:
        raise HTTPException(400, "Chưa có synthesis.")
    gaps = [g for g in syn["gaps"] if g["confirmed"]]
    if not gaps:
        raise HTTPException(400, "Chưa có gap nào được confirm. POST /synthesize/{id}/confirm trước.")
    cfg = await get_config(pid)
    drafts: RQDrafts = await generate_structured(
        P.rq_prompt(proj["plan"], gaps, syn["themes"], cfg["paper_type"]), RQDrafts, system=P.RQ_SYSTEM, temperature=0.5)
    gap_ids = {g["gap_id"] for g in gaps}
    cands = [d for d in drafts.candidates if d.gap_id in gap_ids]
    if not cands:
        raise HTTPException(502, "LLM không trả RQ hợp lệ.")

    # Novelty grounded: lấy paper gần nghĩa nhất trong corpus rồi để LLM so sánh
    index = await build_evidence_index(pid)
    items, any_neigh = [], False
    for i, d in enumerate(cands):
        neigh = [n for n in await closest_papers(pid, d.question) if n in index]
        any_neigh |= bool(neigh)
        items.append({"index": i, "question": d.question, "neighbours": [
            {"id": n, "title": index[n]["title"], "findings": [c["statement"] for c in index[n]["findings"][:3]]} for n in neigh]})
    nov = {}
    if any_neigh:
        res: NoveltyBatch = await generate_structured(P.novelty_prompt(items), NoveltyBatch, temperature=0.1)
        nov = {n.index: n for n in res.items}

    out = []
    for i, d in enumerate(cands):
        n = nov.get(i)
        novelty = ({"score": n.score, "overlap_notes": n.overlap_notes,
                    "closest_paper_ids": [x for x in n.closest_paper_ids if x in index]} if n else
                   {"score": 0, "overlap_notes": "Chưa đánh giá (chưa có full-text embedding).", "closest_paper_ids": []})
        out.append({**d.model_dump(), "novelty": novelty})
    await save_artifact(pid, "rq_candidates", out)
    return out


def best_index(cands: list[dict]) -> int:
    return max(range(len(cands)), key=lambda i: cands[i]["feasibility"]["score"] + cands[i]["novelty"]["score"])


async def select_rq(pid: int, idx: int) -> dict:
    cands = await load_artifact(pid, "rq_candidates")
    if not cands or not (0 <= idx < len(cands)):
        raise HTTPException(400, "Index RQ không hợp lệ.")
    await save_artifact(pid, "rq_selected", cands[idx])
    return cands[idx]


async def run_model(pid: int) -> dict:
    rq = await load_artifact(pid, "rq_selected")
    syn = await load_artifact(pid, "synthesis")
    if not rq or not syn:
        raise HTTPException(400, "Cần synthesis và RQ đã chọn.")
    index = await build_evidence_index(pid)
    res: ConceptualModel = await generate_structured(
        P.model_prompt(rq, syn["themes"], digest(index)), ConceptualModel, system=P.RQ_SYSTEM, temperature=0.3)
    data = res.model_dump()
    for h in data["hypotheses"]:
        h["basis_paper_ids"] = [i for i in h["basis_paper_ids"] if i in index]
    data["hypotheses"] = [h for h in data["hypotheses"] if h["basis_paper_ids"]]   # bỏ giả thuyết không có cơ sở
    await save_artifact(pid, "conceptual_model", data)
    return data


class SelectBody(BaseModel):
    index: int


@router.post("/{project_id}")
async def generate(project_id: int):
    return await run_rq_generation(project_id)


@router.get("/{project_id}")
async def list_candidates(project_id: int):
    return await load_artifact(project_id, "rq_candidates", [])


@router.post("/{project_id}/select")
async def select(project_id: int, body: SelectBody):
    return await select_rq(project_id, body.index)


@router.post("/{project_id}/model")
async def model(project_id: int):
    return await run_model(project_id)
