"""Reviewer #1: kiểm tra mọi citation [paper_id] trong draft có tồn tại trong DB."""
import re
from dataclasses import dataclass, field, asdict

CITE_RE = re.compile(r"\[([A-Za-z0-9_\-:.]+)\]")
META_RE = re.compile(r"\b(this (paper|review|article|study|section)|we |our |in this|the remainder|section \d)", re.I)


@dataclass
class ClaimReport:
    sentence: str
    cited_ids: list[str]
    missing_ids: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | invalid_citation | uncited


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def extract_claims(draft: str) -> list[tuple[str, list[str]]]:
    return [(s, CITE_RE.findall(s)) for s in split_sentences(draft)]


def check_citations(draft: str, known_ids: set[str], require_citation_min_words: int = 8) -> dict:
    """Thuần hàm (dễ test). known_ids = set paper_id có trong DB."""
    reports: list[ClaimReport] = []
    for sentence, ids in extract_claims(draft):
        r = ClaimReport(sentence=sentence, cited_ids=ids)
        if ids:
            r.missing_ids = [i for i in ids if i not in known_ids]
            if r.missing_ids:
                r.status = "invalid_citation"
        elif len(sentence.split()) >= require_citation_min_words and not META_RE.search(sentence):
            r.status = "uncited"   # câu dài, có vẻ là claim nhưng không trích dẫn
        reports.append(r)
    bad = [r for r in reports if r.status != "ok"]
    return {
        "passed": not any(r.status == "invalid_citation" for r in reports),
        "n_claims": len(reports),
        "n_invalid": sum(r.status == "invalid_citation" for r in reports),
        "n_uncited": sum(r.status == "uncited" for r in reports),
        "issues": [asdict(r) for r in bad],
    }
