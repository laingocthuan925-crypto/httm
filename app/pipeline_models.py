"""
Schema cho các bước sau Planner. Các model dùng làm response_schema của Gemini
cố ý KHÔNG có giá trị default (SDK/Gemini hay lỗi với default) — dùng Optional[...] cho nullable.
"""
from typing import List, Optional
from pydantic import BaseModel


# ---------- Analyst ----------
class Evidence(BaseModel):
    chunk_ref: str        # nhãn đoạn text được cung cấp, vd "C123" hoặc "ABSTRACT"
    quote: str            # trích NGUYÊN VĂN từ đoạn đó (<= 40 từ)


class ExtractedClaim(BaseModel):
    statement: str
    claim_type: str       # finding | method | definition | limitation | theory
    evidence: List[Evidence]


class PaperAnalysis(BaseModel):
    research_question: Optional[str]
    method: Optional[str]
    sample_or_data: Optional[str]
    theoretical_lens: Optional[str]
    key_findings: List[ExtractedClaim]
    limitations: List[str]
    not_reported: List[str]


# ---------- Screening ----------
class ScreenDecision(BaseModel):
    paper_id: str
    include: bool
    reason: str


class ScreenBatch(BaseModel):
    decisions: List[ScreenDecision]


# ---------- Synthesis ----------
class Theme(BaseModel):
    name: str
    summary: str
    paper_ids: List[str]


class Contradiction(BaseModel):
    topic: str
    position_a: str
    position_b: str
    paper_ids: List[str]


class Gap(BaseModel):
    gap_id: str
    description: str
    gap_type: str         # population | method | context | theory | contradiction | other
    paper_ids: List[str]
    confirmed: bool


class Synthesis(BaseModel):
    themes: List[Theme]
    consensus: List[str]
    contradictions: List[Contradiction]
    gaps: List[Gap]


# ---------- Research questions / model ----------
class Feasibility(BaseModel):
    score: int            # 1-5
    data_availability: str
    scope_notes: str


class RQDraft(BaseModel):
    question: str
    gap_id: str
    rationale: str
    study_design: str
    feasibility: Feasibility


class RQDrafts(BaseModel):
    candidates: List[RQDraft]


class NoveltyItem(BaseModel):
    index: int
    score: int            # 1-5 (5 = rất mới so với corpus)
    overlap_notes: str
    closest_paper_ids: List[str]


class NoveltyBatch(BaseModel):
    items: List[NoveltyItem]


class Variable(BaseModel):
    name: str
    definition: str
    measurement: str


class Hypothesis(BaseModel):
    hypothesis_id: str
    statement: str
    independent_variable: str
    dependent_variable: str
    moderator: Optional[str]
    expected_direction: str   # positive | negative | curvilinear | non-directional
    basis_paper_ids: List[str]


class ConceptualModel(BaseModel):
    independent_variables: List[Variable]
    dependent_variables: List[Variable]
    mediators: List[Variable]
    moderators: List[Variable]
    controls: List[Variable]
    hypotheses: List[Hypothesis]
    rationale: str


# ---------- Writer ----------
class KeyPoint(BaseModel):
    point: str
    paper_ids: List[str]


class OutlineSection(BaseModel):
    key: str
    heading: str
    purpose: str
    key_points: List[KeyPoint]


class Outline(BaseModel):
    title: str
    sections: List[OutlineSection]


class SectionOutput(BaseModel):
    text: str
    summary: str              # 2-3 câu: mục này đã nói gì (làm "bộ nhớ" cho mục sau)
    defined_terms: List[str]


class StyleProfile(BaseModel):
    voice: str
    tense_habits: str
    sentence_length: str
    paragraph_habits: str
    hedging_and_stance: str
    transitions: str
    terminology: List[str]
    notes: str


# ---------- Reviewer ----------
class ClaimVerdict(BaseModel):
    index: int
    verdict: str              # supported | partial | unsupported
    reason: str


class ClaimVerdicts(BaseModel):
    verdicts: List[ClaimVerdict]


class StructureIssue(BaseModel):
    section_key: str
    severity: str             # high | medium | low
    issue: str
    fix: str


class StructureReview(BaseModel):
    rq_answered: bool
    issues: List[StructureIssue]
