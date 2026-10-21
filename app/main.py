"""Entry point: uvicorn app.main:app --reload --port 8000"""
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI

from app.db import connect_db, close_db
from app.routers import (planner, search, reader, analysis, synthesis,
                         rq_generator, writer, reviewer, export, pipeline)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="Research Copilot API",
    description="Từ tài liệu → bài báo có dẫn chứng kiểm chứng được.",
    version="0.2.0",
    lifespan=lifespan,
)

for r in (planner, search, reader, analysis, synthesis, rq_generator, writer, reviewer, export, pipeline):
    app.include_router(r.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
