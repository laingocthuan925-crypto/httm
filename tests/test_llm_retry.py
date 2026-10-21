from tenacity import wait_none
from app.services.llm_retry import llm_retry, is_retryable


class Fake503(Exception):
    code = 503


def test_is_retryable():
    assert is_retryable(Fake503())
    assert not is_retryable(ValueError("bad json"))


async def test_retries_then_succeeds():
    calls = {"n": 0}

    @llm_retry
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Fake503()
        return "ok"

    flaky.retry.wait = wait_none()
    assert await flaky() == "ok" and calls["n"] == 3
