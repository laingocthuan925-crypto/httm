"""Reviewer: câu nào có trích dẫn thì bằng chứng của paper đó có thật sự ủng hộ câu đó không?"""
from app.pipeline_models import ClaimVerdicts
from app.services.citation_checker import extract_claims
from app.services.llm import generate_structured
from app.services import prompts as P


def evidence_text(index: dict, pid_: str) -> str:
    p = index.get(pid_)
    if not p:
        return ""
    lines = [f"design: {p['method']}; sample: {p['sample']}"]
    for c in p["findings"]:
        q = c["evidence"][0]["quote"] if c.get("evidence") else ""
        lines.append(f"{c['statement']} (quote: \"{q}\")")
    return "\n".join(lines)


async def verify_section(text: str, index: dict, batch: int = 12) -> list[dict]:
    items = []
    for sent, ids in extract_claims(text):
        ids = [i for i in ids if i in index]
        if ids:
            items.append({"sentence": sent, "ids": ids})
    issues = []
    for s in range(0, len(items), batch):
        chunk = items[s:s + batch]
        prompt = P.claim_verify_prompt([
            {"i": k, "sentence": it["sentence"],
             "evidence": {i: evidence_text(index, i) for i in it["ids"]}} for k, it in enumerate(chunk)])
        res: ClaimVerdicts = await generate_structured(prompt, ClaimVerdicts, system=P.VERIFIER_SYSTEM, temperature=0.0)
        for v in res.verdicts:
            if 0 <= v.index < len(chunk) and v.verdict != "supported":
                issues.append({"sentence": chunk[v.index]["sentence"], "verdict": v.verdict, "reason": v.reason})
    return issues
