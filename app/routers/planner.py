"""Module 2: Research Planner. Topic -> ResearchPlan (structured output) -> lưu DB."""
import json
from fastapi import APIRouter, HTTPException

from app.models import ResearchPlanRequest, ResearchPlanResponse, ResearchPlan
from app.db import get_pool
from app.services.llm import generate_structured

router = APIRouter(prefix="/plan", tags=["planner"])

PLANNER_SYSTEM = (
    "You are a research methodologist. Turn a topic into a rigorous, searchable research plan. "
    "Keywords and synonyms must be English academic search terms (short, 1-3 words each). "
    "Research questions must be specific and answerable, not generic 'impact of X on Y'."
)


async def generate_research_plan(payload: ResearchPlanRequest) -> ResearchPlan:
    prompt = (
        f"Chủ đề nghiên cứu: {payload.topic}\n"
        f"Ngôn ngữ mong muốn cho tài liệu: {payload.language}\n"
        f"Loại nghiên cứu mong muốn: {payload.study_type or 'không chỉ định'}\n"
        f"Số lượng paper mục tiêu: {payload.target_paper_count}\n"
        f"Journal/conference mục tiêu: {payload.target_venue or 'không chỉ định'}\n\n"
        "Phân tích chủ đề thành research plan: lĩnh vực, từ khoá tìm kiếm (tiếng Anh), từ đồng nghĩa cho mỗi từ khoá, "
        "câu hỏi nghiên cứu khả thi, chiến lược tìm kiếm (nguồn dữ liệu, khoảng thời gian, loại nghiên cứu)."
    )
    return await generate_structured(prompt, ResearchPlan, system=PLANNER_SYSTEM, temperature=0.3)


@router.post("", response_model=ResearchPlanResponse)
async def create_plan(payload: ResearchPlanRequest) -> ResearchPlanResponse:
    plan = await generate_research_plan(payload)
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO research_projects (topic, research_plan) VALUES ($1, $2::jsonb) RETURNING id;",
            payload.topic, json.dumps(plan.model_dump()))
    return ResearchPlanResponse(id=row["id"], plan=plan)


@router.get("/{project_id}", response_model=ResearchPlanResponse)
async def get_plan(project_id: int) -> ResearchPlanResponse:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("SELECT id, research_plan FROM research_projects WHERE id = $1;", project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy research project.")
    rp = row["research_plan"]
    plan = ResearchPlan.model_validate(json.loads(rp) if isinstance(rp, str) else rp)
    return ResearchPlanResponse(id=row["id"], plan=plan)
