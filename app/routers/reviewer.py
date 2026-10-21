"""Reviewer Agents: citation checker, claim verifier, style checker, structure reviewer."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.pipeline_models import StructureReview
from app.services.citation_checker import CITE_RE, check_citations
from app.services.claim_verifier import verify_section
from app.services.evidence import build_evidence_index
from app.services.llm import generate_structured
from app.services.store import get_project, save_artifact, load_artifact
from app.services.style_checks import analyze_style
from app.services import prompts as P

router = APIRouter(prefix="/review", tags=["reviewer"])


class DraftIn(BaseModel):
    draft: str


@router.post("/citations")                     # giữ nguyên endpoint cũ (kiểm tra theo toàn DB)
async def review_citations(body: DraftIn):
    cited = sorted(set(CITE_RE.findall(body.draft)))
    known: set[str] = set()
    if cited:
        async with get_pool().acquire() as conn:
            rows = await conn.fetch("SELECT id FROM papers WHERE id = ANY($1::text[])", cited)
        known = {r["id"] for r in rows}
    return check_citations(body.draft, known)


async def run_review(pid: int) -> dict:
    draft = await load_artifact(pid, "draft")
    if not draft:
        raise HTTPException(400, "Chưa có draft.")
    proj = await get_project(pid)
    index = await build_evidence_index(pid)
    known = set(index)
    sections = {}
    for key in draft["order"]:
        text = draft["sections"][key]["text"]
        sections[key] = {
            "citations": check_citations(text, known),
            "claims": await verify_section(text, index),
            "style": analyze_style(text),
        }
    full = "\n\n".join(f"## [{k}] {draft['sections'][k]['heading']}\n{draft['sections'][k]['text']}" for k in draft["order"])
    rq = "; ".join(proj["plan"].get("research_questions", []))
    sr: StructureReview = await generate_structured(P.structure_review_prompt(full, rq), StructureReview,
                                                    temperature=0.1)
    review = {
        "sections": sections,
        "structure": sr.model_dump(),
        "summary": {
            "invalid_citations": sum(s["citations"]["n_invalid"] for s in sections.values()),
            "unsupported_or_partial_claims": sum(len(s["claims"]) for s in sections.values()),
            "style_flags": sum(len(s["style"]["flags"]) for s in sections.values()),
            "structure_issues": len(sr.issues),
            "rq_answered": sr.rq_answered,
        },
    }
    review["summary"]["passed"] = (review["summary"]["invalid_citations"] == 0
                                   and review["summary"]["unsupported_or_partial_claims"] == 0
                                   and review["summary"]["style_flags"] == 0
                                   and not any(i["severity"] == "high" for i in review["structure"]["issues"]))
    await save_artifact(pid, "review", review)
    return review


def issues_for(review: dict, key: str) -> list[str]:
    s = review["sections"].get(key)
    if not s:
        return []
    out = []
    for i in s["citations"]["issues"]:
        if i["status"] == "invalid_citation":
            out.append(f"Citation id(s) {i['missing_ids']} are not in the evidence set — remove or replace: \"{i['sentence'][:160]}\"")
        elif i["status"] == "uncited":
            out.append(f"Factual sentence lacks a citation (add one from the pack or remove it): \"{i['sentence'][:160]}\"")
    for c in s["claims"]:
        out.append(f"Claim is {c['verdict']} by its cited evidence ({c['reason']}): \"{c['sentence'][:160]}\"")
    out += s["style"]["flags"]
    out += [f"[{i['severity']}] {i['issue']} -> {i['fix']}" for i in review["structure"]["issues"] if i["section_key"] == key]
    return out[:25]


@router.post("/{project_id}")
async def review(project_id: int):
    return await run_review(project_id)


@router.get("/{project_id}")
async def get_review(project_id: int):
    return await load_artifact(project_id, "review") or {}
