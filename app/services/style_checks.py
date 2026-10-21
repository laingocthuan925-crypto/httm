"""Kiểm tra văn phong bằng số liệu (không cần LLM): bắt các 'dấu hiệu' của văn bản máy."""
import re
import statistics
from collections import Counter
from app.services.citation_checker import split_sentences

BANNED = [
    "delve", "in today's rapidly evolving", "it is important to note", "it is worth noting",
    "plays a crucial role", "plays a pivotal role", "a testament to", "tapestry", "in the realm of",
    "shed light on", "underscores the importance", "paradigm shift", "multifaceted",
    "navigate the complexities", "ever-evolving", "in the ever-changing", "cutting-edge",
    "game-changer", "unlock the potential", "holistic understanding",
]
TRANSITIONS = ("moreover", "furthermore", "additionally", "in addition", "overall", "in conclusion")


def _cv(xs):
    return statistics.pstdev(xs) / statistics.mean(xs) if len(xs) > 2 and statistics.mean(xs) else 1.0


def analyze_style(text: str) -> dict:
    low = text.lower()
    sents = split_sentences(text)
    lens = [len(s.split()) for s in sents]
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    plens = [len(p.split()) for p in paras]
    openers = Counter(" ".join(s.lower().split()[:2]) for s in sents if len(s.split()) > 3)
    trans_ratio = sum(s.lower().startswith(TRANSITIONS) for s in sents) / max(len(sents), 1)
    banned = [b for b in BANNED if b in low]

    flags = []
    if len(sents) >= 8 and _cv(lens) < 0.35:
        flags.append("Độ dài câu quá đều nhau — trộn câu ngắn và câu dài.")
    if len(paras) >= 4 and _cv(plens) < 0.2:
        flags.append("Độ dài đoạn văn quá đều nhau.")
    if banned:
        flags.append("Có cụm sáo rỗng đặc trưng văn máy: " + ", ".join(banned))
    if trans_ratio > 0.2:
        flags.append("Lạm dụng từ nối đầu câu (Moreover/Furthermore/Additionally...).")
    rep = [o for o, n in openers.items() if n >= 4]
    if rep:
        flags.append("Nhiều câu mở đầu giống nhau: " + ", ".join(rep))
    return {
        "n_sentences": len(sents),
        "mean_sentence_len": round(statistics.mean(lens), 1) if lens else 0,
        "sentence_len_cv": round(_cv(lens), 2),
        "n_paragraphs": len(paras),
        "banned_found": banned,
        "flags": flags,
    }
