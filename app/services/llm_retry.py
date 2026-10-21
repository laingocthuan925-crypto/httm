"""Retry cho lỗi tạm thời của Gemini (503/429/500...).
Dùng: bọc hàm gọi API trong llm.py bằng @llm_retry, hoặc gọi qua call_with_retry.
"""
import logging
from tenacity import (
    retry, stop_after_attempt, wait_exponential_jitter,
    retry_if_exception, before_sleep_log,
)

log = logging.getLogger(__name__)
RETRYABLE_CODES = {429, 500, 502, 503, 504}


def is_retryable(exc: BaseException) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in RETRYABLE_CODES:
        return True
    msg = str(exc).upper()
    return any(k in msg for k in ("503", "UNAVAILABLE", "OVERLOADED", "RESOURCE_EXHAUSTED"))


llm_retry = retry(
    retry=retry_if_exception(is_retryable),
    stop=stop_after_attempt(4),                       # 1 lần + 3 lần retry
    wait=wait_exponential_jitter(initial=2, max=20),  # 2s, 4s, 8s (+jitter)
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)

# Ví dụ trong llm.py:
#   @llm_retry
#   async def _call_gemini(...): ...
#   -> generate_structured() gọi _call_gemini(); lỗi JSON/validation KHÔNG bị retry ở đây.
