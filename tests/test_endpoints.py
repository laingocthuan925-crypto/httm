import json
from app.models import ResearchPlan, SearchStrategy, KeywordSynonyms

PLAN = ResearchPlan(
    topic="AI và sinh viên", research_domain="Education", keywords=["AI"],
    synonyms=[KeywordSynonyms(keyword="AI", synonyms=["artificial intelligence"])],
    research_questions=["RQ1?"],
    search_strategy=SearchStrategy(databases=["OpenAlex"], date_range="2020-2025",
                                   language=["en"], study_types=["survey"], target_paper_count=50),
)


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_plan_create_and_get(client, store, monkeypatch):
    async def fake_gen(payload): return PLAN
    monkeypatch.setattr("app.routers.planner.generate_research_plan", fake_gen)
    r = await client.post("/plan", json={"topic": "AI và sinh viên"})
    assert r.status_code == 200 and r.json()["plan"]["research_domain"] == "Education"
    store["plan_json"] = json.dumps(PLAN.model_dump())
    r = await client.get("/plan/1")
    assert r.status_code == 200 and r.json()["id"] == 1


async def test_plan_404(client):
    assert (await client.get("/plan/999")).status_code == 404


async def test_plan_validation_error(client):
    assert (await client.post("/plan", json={})).status_code == 422


async def test_review_citations_endpoint(client):
    r = await client.post("/review/citations", json={
        "draft": "AI improves student productivity in higher education [W1]. Another finding here [W9]."})
    body = r.json()
    assert r.status_code == 200 and not body["passed"]
    assert body["issues"][0]["missing_ids"] == ["W9"]

# TODO khi /search /analyze /synthesize được push: thêm test tương tự (mock LLM + OpenAlex).
