"""Chống bịa: kiểm tra quote LLM trích có thật sự nằm trong đoạn nguồn không."""
import re
from difflib import SequenceMatcher


def _norm(s: str) -> str:
    s = s.lower().replace("\u00ad", "")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_supported(quote: str, source: str, min_cover: float = 0.85, min_block: int = 8) -> bool:
    """True nếu quote nằm trong source (cho phép lệch nhỏ: bỏ/đổi 1-2 từ).
    Cộng tổng độ dài các khối khớp >= min_block ký tự; khối lẻ tẻ ngắn không được tính
    nên quote bịa không 'ăn may' qua các mảnh vụn."""
    q, s = _norm(quote), _norm(source)
    if len(q) < 15 or not s:
        return False
    if q in s:
        return True
    blocks = SequenceMatcher(None, q, s, autojunk=False).get_matching_blocks()
    covered = sum(b.size for b in blocks if b.size >= min_block)
    return covered / len(q) >= min_cover
