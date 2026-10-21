import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


class FakeConn:
    def __init__(self, store): self.store = store
    async def fetchrow(self, q, *a):
        if q.lstrip().upper().startswith("INSERT"):
            self.store["saved"] = a
            return {"id": 1}
        if self.store.get("plan_json"):
            return {"id": 1, "research_plan": self.store["plan_json"]}
        return None
    async def fetch(self, q, *a):
        return [{"id": i} for i in a[0] if i in self.store.get("papers", set())]


class FakePool:
    def __init__(self, store): self.store = store
    def acquire(self):
        conn = FakeConn(self.store)
        class Ctx:
            async def __aenter__(s): return conn
            async def __aexit__(s, *e): return False
        return Ctx()


@pytest.fixture
def store(monkeypatch):
    st = {"papers": {"W1", "W2"}}
    pool = FakePool(st)
    monkeypatch.setattr("app.routers.planner.get_pool", lambda: pool)
    monkeypatch.setattr("app.routers.reviewer.get_pool", lambda: pool)
    return st


@pytest.fixture
async def client(store):
    # ASGITransport không chạy lifespan -> không cần DB thật
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
