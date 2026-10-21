"""Helper gọi Gemini dùng chung: structured output + retry 503/429."""
import os
import logging
from fastapi import HTTPException
from google import genai
from google.genai import types

from app.services.llm_retry import llm_retry

log = logging.getLogger(__name__)
_client = None


def _get_client():
    global _client
    if _client is None:                       # lazy: import module không cần API key
        _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client


def default_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3-pro-preview")


@llm_retry
async def _call(model, contents, config):
    return await _get_client().aio.models.generate_content(model=model, contents=contents, config=config)


async def generate_structured(prompt: str, schema, *, system: str | None = None, temperature: float = 0.2):
    """Trả object Pydantic đã validate. Lỗi -> HTTP 502."""
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json", response_schema=schema,
        system_instruction=system, temperature=temperature,
    )
    try:
        resp = await _call(default_model(), prompt, cfg)
    except Exception as exc:
        log.error("Gemini lỗi: %s", exc)
        raise HTTPException(status_code=502, detail="Không gọi được Gemini API.")
    if resp.parsed is None:
        log.error("Gemini không trả JSON đúng schema: %s", resp.text)
        raise HTTPException(status_code=502, detail="LLM không trả về kết quả hợp lệ.")
    return resp.parsed
