"""Scientific Writer: outline -> viết từng mục (Claim->Evidence) -> abstract -> (revise theo review)."""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.pipeline_models import Outline, OutlineSection, SectionOutput, StyleProfile
from app.services.evidence import build_evidence_index, build_process_data, format_pack
from app.services.llm import generate_structured
from app.services.store import get_project, save_artifact, load_artifact, get_config
from app.services.citation_checker import CITE_RE
from app.services import prompts as P

router = APIRouter(prefix="/writer", tags=["writer"])

TEMPLATES = {
    "systematic_review": [("introduction", "Introduction"), ("methodology", "Methodology"), ("findings", "Findings"),
                          ("discussion", "Discussion"), ("limitations", "Limitations and Future Research"), ("conclusion", "Conclusion")],
    "narrative_review": [("introduction", "Introduction"), ("background", "Theoretical Background"),
                         ("thematic_synthesis", "Thematic Synthesis"), ("discussion", "Discussion"), ("conclusion", "Conclusion")],
    "conceptual": [("introduction", "Introduction"), ("literature_review", "Literature Review"),
                   ("conceptual_model", "Conceptual Model and Propositions"), ("discussion", "Discussion"), ("conclusion", "Conclusion")],
}
WORDS = {"introduction": 900, "methodology": 700, "findings": 1800, "thematic_synthesis": 1800, "background": 1200,
         "literature_review": 1200, "conceptual_model": 1200, "discussion": 1000, "limitations": 500, "conclusion": 500}


def _template(cfg: dict):
    if cfg["paper_type"] not in TEMPLATES:
        raise HTTPException(400, f"paper_type '{cfg['paper_type']}' chưa hỗ trợ. Hỗ trợ: {list(TEMPLATES)} "
                                 "(bài thực nghiệm cần dữ liệu người dùng — chưa có trong V1).")
    return TEMPLATES[cfg["paper_type"]]


async def rq_text(pid: int, plan: dict) -> str:
    sel = await load_artifact(pid, "rq_selected")
    return sel["question"] if sel else "; ".join(plan.get("research_questions", []))


async def style_text(pid: int) -> str:
    sp = await load_artifact(pid, "style_profile")
    if not sp:
        return P.DEFAULT_STYLE
    return "; ".join(f"{k}: {v}" for k, v in sp.items() if v)


async def run_outline(pid: int) -> dict:
    proj, cfg = await get_project(pid), await get_config(pid)
    template = _template(cfg)
    syn = await load_artifact(pid, "synthesis")
    if not syn:
        raise HTTPException(400, "Chưa có synthesis.")
    index = await build_evidence_index(pid)
    gaps = [g for g in syn["gaps"] if g["confirmed"]]
    res: Outline = await generate_structured(
        P.outline_prompt(proj["plan"], await rq_text(pid, proj["plan"]), syn["themes"], gaps, template, list(index)),
        Outline, temperature=0.4)
    by_key = {s.key: s for s in res.sections}
    sections = []
    for key, heading in template:                          # ép đúng cấu trúc + bỏ id bịa
        s = by_key.get(key) or OutlineSection(key=key, heading=heading, purpose="", key_points=[])
        d = s.model_dump()
        d["heading"] = heading
        for kp in d["key_points"]:
            kp["paper_ids"] = [i for i in kp["paper_ids"] if i in index]
        sections.append(d)
    out = {"title": res.title, "sections": sections}
    await save_artifact(pid, "outline", out)
    return out


async def _ctx(pid: int) -> dict:
    proj, cfg = await get_project(pid), await get_config(pid)
    cm = await load_artifact(pid, "conceptual_model")
    return {"plan": proj["plan"], "cfg": cfg, "index": await build_evidence_index(pid),
            "style": await style_text(pid), "rq": await rq_text(pid, proj["plan"]),
            "process": await build_process_data(pid, proj["plan"]),
            "model_text": json.dumps(cm, ensure_ascii=False, indent=1) if cm else ""}


def _system(ctx: dict) -> str:
    return P.writer_system(ctx["cfg"]["language"], ctx["cfg"]["venue"], ctx["style"])


async def _write_one(section: dict, title: str, ctx: dict, memory: list[str]) -> dict:
    ids = [i for kp in section["key_points"] for i in kp["paper_ids"]]
    key = section["key"]
    prompt = P.section_prompt(
        section, title, format_pack(ctx["index"], ids), "\n".join(memory), ctx["rq"],
        ctx["process"] if key in ("methodology", "limitations") else "",
        ctx["model_text"] if key == "conceptual_model" else "", WORDS.get(key, 800))
    out: SectionOutput = await generate_structured(prompt, SectionOutput, system=_system(ctx), temperature=0.6)
    return {"heading": section["heading"], "text": out.text.strip(), "summary": out.summary, "defined_terms": out.defined_terms}


async def run_draft(pid: int) -> dict:
    outline = await load_artifact(pid, "outline") or await run_outline(pid)
    ctx = await _ctx(pid)
    sections, memory = {}, []
    for s in outline["sections"]:
        sec = await _write_one(s, outline["title"], ctx, memory)
        sections[s["key"]] = sec
        memory.append(f"- {sec['heading']}: {sec['summary']} (terms: {', '.join(sec['defined_terms']) or '-'})")
    full = "\n\n".join(f"## {v['heading']}\n{v['text']}" for v in sections.values())
    abs_sec = {"key": "abstract", "heading": "Abstract", "purpose": "Summarise the whole paper", "key_points": []}
    ab = await _write_one(abs_sec, outline["title"], ctx, ["FULL PAPER TEXT:\n" + full])
    draft = {"title": outline["title"], "order": [s["key"] for s in outline["sections"]],
             "sections": sections, "abstract": ab["text"]}
    await save_artifact(pid, "draft", draft)
    return draft


async def run_revision(pid: int) -> dict:
    from app.routers.reviewer import issues_for
    draft, review, outline = (await load_artifact(pid, "draft"), await load_artifact(pid, "review"),
                              await load_artifact(pid, "outline"))
    if not (draft and review and outline):
        raise HTTPException(400, "Cần draft + review trước khi revise.")
    ctx = await _ctx(pid)
    osec = {s["key"]: s for s in outline["sections"]}
    changed = []
    for key in draft["order"]:
        issues = issues_for(review, key)
        if not issues:
            continue
        text = draft["sections"][key]["text"]
        ids = [i for kp in osec[key]["key_points"] for i in kp["paper_ids"]] + CITE_RE.findall(text)
        out: SectionOutput = await generate_structured(
            P.revise_prompt(text, issues, format_pack(ctx["index"], ids)), SectionOutput, system=_system(ctx), temperature=0.4)
        draft["sections"][key].update(text=out.text.strip(), summary=out.summary, defined_terms=out.defined_terms)
        changed.append(key)
    if changed:
        await save_artifact(pid, "draft", draft)
    return {"revised_sections": changed}


class StyleBody(BaseModel):
    samples: list[str]        # đoạn văn mẫu từ journal mục tiêu (3-5 đoạn dài)


@router.post("/{project_id}/style-profile")
async def style_profile(project_id: int, body: StyleBody):
    sp: StyleProfile = await generate_structured(P.style_profile_prompt(body.samples), StyleProfile, temperature=0.2)
    await save_artifact(project_id, "style_profile", sp.model_dump())
    return sp


@router.post("/{project_id}/outline")
async def outline(project_id: int):
    return await run_outline(project_id)


@router.get("/{project_id}/outline")
async def get_outline(project_id: int):
    return await load_artifact(project_id, "outline") or {}


@router.post("/{project_id}/draft")
async def draft(project_id: int):
    return await run_draft(project_id)


@router.get("/{project_id}/draft")
async def get_draft(project_id: int):
    return await load_artifact(project_id, "draft") or {}


@router.post("/{project_id}/revise")
async def revise(project_id: int):
    return await run_revision(project_id)
