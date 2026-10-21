import re
import fitz  # PyMuPDF


def extract_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [(i + 1, p.get_text("text")) for i, p in enumerate(doc)]
    finally:
        doc.close()


def clean(text: str) -> str:
    text = re.sub(r"-\n(\w)", r"\1", text)       # nối từ bị ngắt dòng
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_pages(pages: list[tuple[int, str]], max_chars: int = 1800, overlap: int = 200) -> list[dict]:
    """Chunk theo đoạn, gộp đến max_chars, giữ số trang. Bỏ PDF scan (gần như không có text)."""
    chunks, buf, buf_page = [], "", None
    for page, raw in pages:
        for para in re.split(r"\n\s*\n", clean(raw)):
            para = para.strip().replace("\n", " ")
            if len(para) < 40:
                continue
            if buf and len(buf) + len(para) > max_chars:
                chunks.append({"page": buf_page, "text": buf})
                buf, buf_page = buf[-overlap:], page
            buf = f"{buf} {para}".strip()
            buf_page = buf_page or page
    if buf:
        chunks.append({"page": buf_page, "text": buf})
    return chunks if sum(len(c["text"]) for c in chunks) > 1500 else []
