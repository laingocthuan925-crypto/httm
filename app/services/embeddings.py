import os
from google import genai
from google.genai import types
from app.services.llm_retry import llm_retry

MODEL = "gemini-embedding-001"
DIM = 768
_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


@llm_retry
def _embed_batch(texts: list[str], task_type: str) -> list[list[float]]:
    res = _client.models.embed_content(
        model=MODEL, contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIM),
    )
    return [e.values for e in res.embeddings]


def embed_documents(texts: list[str], batch: int = 50) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), batch):
        out += _embed_batch(texts[i:i + batch], "RETRIEVAL_DOCUMENT")
    return out


def embed_query(text: str) -> list[float]:
    return _embed_batch([text], "RETRIEVAL_QUERY")[0]
