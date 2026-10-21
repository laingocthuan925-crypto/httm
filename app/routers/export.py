from fastapi import APIRouter, HTTPException, Response

from app.services.evidence import build_evidence_index
from app.services.exporter import assemble, to_markdown, to_docx
from app.services.store import load_artifact

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/{project_id}")
async def export(project_id: int, format: str = "md"):
    draft = await load_artifact(project_id, "draft")
    if not draft:
        raise HTTPException(404, "Chưa có draft.")
    doc = assemble(draft, await build_evidence_index(project_id))
    if format == "docx":
        return Response(to_docx(doc), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f"attachment; filename=paper_{project_id}.docx"})
    return Response(to_markdown(doc), media_type="text/markdown; charset=utf-8")
