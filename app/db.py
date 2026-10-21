"""
PostgreSQL (asyncpg pool) + schema.
Thiết kế: papers là bảng GLOBAL (metadata), project_papers gắn paper vào project
(kèm trạng thái sàng lọc). Kết quả các bước (synthesis, outline, draft...) lưu ở
project_artifacts dạng JSONB để đổi schema không cần migration.
"""
import os
import asyncpg
from typing import Optional
from pgvector.asyncpg import register_vector

_pool: Optional[asyncpg.Pool] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS research_projects (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    research_plan   JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'planned',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS papers (
    id              TEXT PRIMARY KEY,           -- dạng ngắn: W123 (OpenAlex) hoặc S2_xxx
    title           TEXT NOT NULL,
    abstract        TEXT,
    year            INTEGER,
    doi             TEXT,
    oa_url          TEXT,
    source          TEXT NOT NULL DEFAULT 'openalex',
    authors         JSONB NOT NULL DEFAULT '[]',
    venue           TEXT,
    citation_count  INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS papers_doi_idx ON papers(doi);

CREATE TABLE IF NOT EXISTS project_papers (
    project_id      INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
    paper_id        TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    screen_status   TEXT NOT NULL DEFAULT 'candidate',  -- candidate|included|excluded
    screen_reason   TEXT,
    PRIMARY KEY (project_id, paper_id)
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id          SERIAL PRIMARY KEY,
    paper_id    TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page        INTEGER,
    chunk_text  TEXT NOT NULL,
    embedding   vector(768) NOT NULL,
    UNIQUE (paper_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS paper_chunks_paper_idx ON paper_chunks(paper_id);

CREATE TABLE IF NOT EXISTS paper_analyses (
    project_id  INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    analysis    JSONB NOT NULL,
    source      TEXT NOT NULL,                  -- full_text | abstract
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, paper_id)
);

-- Log tìm kiếm THẬT, để phần Methodology chỉ mô tả đúng những gì đã làm.
CREATE TABLE IF NOT EXISTS search_runs (
    id          SERIAL PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    query       TEXT NOT NULL,
    n_results   INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_artifacts (
    project_id  INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,   -- config|synthesis|rq_candidates|rq_selected|conceptual_model|style_profile|outline|draft|review|job
    data        JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, kind)
);
"""


async def connect_db() -> None:
    global _pool
    url = os.environ["DATABASE_URL"]
    c = await asyncpg.connect(url)            # extension phải có trước register_vector
    try:
        await c.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    finally:
        await c.close()
    _pool = await asyncpg.create_pool(dsn=url, min_size=1, max_size=10, init=register_vector)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool chưa được khởi tạo. Gọi connect_db() trước.")
    return _pool
