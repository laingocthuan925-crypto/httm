"""Chỉ mục bằng chứng của project: nguồn duy nhất mà Writer/Reviewer được phép dựa vào."""
import json
from app.db import get_pool
from app.services.store import load_artifact


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


async def build_evidence_index(pid: int) -> dict[str, dict]:
    async with get_pool().acquire() as c:
        rows = await c.fetch(
            "SELECT p.id, p.title, p.year, p.authors, p.doi, p.venue, a.analysis, a.source "
            "FROM project_papers pp JOIN papers p ON p.id=pp.paper_id "
            "LEFT JOIN paper_analyses a ON a.paper_id=p.id AND a.project_id=pp.project_id "
            "WHERE pp.project_id=$1 AND pp.screen_status='included' ORDER BY p.year DESC NULLS LAST", pid)
    idx = {}
    for r in rows:
        an = _j(r["analysis"]) if r["analysis"] else {}
        idx[r["id"]] = {
            "id": r["id"], "title": r["title"], "year": r["year"], "authors": _j(r["authors"]) or [],
            "doi": r["doi"], "venue": r["venue"], "source": r["source"] or "none",
            "method": an.get("method"), "sample": an.get("sample_or_data"),
            "findings": an.get("key_findings", []), "limitations": an.get("limitations", []),
        }
    return idx


def format_pack(index: dict, ids: list[str], max_claims: int = 4) -> str:
    """Gói bằng chứng đưa cho Writer. Mỗi dòng bắt đầu bằng [paper_id] — ID duy nhất được phép trích."""
    from app.services.citations import inline_cite
    lines = []
    for pid_ in dict.fromkeys(ids):
        p = index.get(pid_)
        if not p:
            continue
        head = f"[{pid_}] {inline_cite(p)} — \"{p['title']}\" (evidence base: {p['source']})"
        if p["method"] or p["sample"]:
            head += f"\n   design: {p['method'] or 'n/r'}; sample/data: {p['sample'] or 'n/r'}"
        lines.append(head)
        for c in p["findings"][:max_claims]:
            q = c["evidence"][0]["quote"] if c.get("evidence") else ""
            lines.append(f"   - {c['claim_type'].upper()}: {c['statement']}  | quote: \"{q}\"")
    return "\n".join(lines)


async def build_process_data(pid: int, plan: dict) -> str:
    """Số liệu quy trình THẬT cho phần Methodology/Limitations."""
    async with get_pool().acquire() as c:
        runs = await c.fetch("SELECT source, query, n_results, created_at FROM search_runs WHERE project_id=$1 ORDER BY id", pid)
        st = await c.fetch("SELECT screen_status, count(*) n FROM project_papers WHERE project_id=$1 GROUP BY 1", pid)
        src = await c.fetch("SELECT source, count(*) n FROM paper_analyses WHERE project_id=$1 GROUP BY 1", pid)
    s = plan.get("search_strategy", {})
    out = [f"Databases queried: {sorted({r['source'] for r in runs})}",
           f"Planned date range: {s.get('date_range')}; languages: {s.get('language')}; study types: {s.get('study_types')}"]
    for r in runs:
        out.append(f"Search run ({r['created_at']:%Y-%m-%d}) on {r['source']}: query=\"{r['query']}\" -> {r['n_results']} records")
    out.append("Screening counts: " + ", ".join(f"{r['screen_status']}={r['n']}" for r in st))
    out.append("Evidence base of analysed papers: " + ", ".join(f"{r['source']}={r['n']}" for r in src))
    out.append("Screening and data extraction were performed with a large language model (Google Gemini); "
               "every extracted finding carries a verbatim quote that was programmatically checked against the source text.")
    return "\n".join(out)


async def evidence_for_ids(pid: int, ids: list[str]) -> str:
    return format_pack(await build_evidence_index(pid), ids)
