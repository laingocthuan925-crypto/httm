import httpx

MAX_BYTES = 30 * 1024 * 1024
HEADERS = {"User-Agent": "research-agent/0.1 (mailto:team@example.com)"}


async def fetch_pdf(url: str | None, client: httpx.AsyncClient | None = None) -> bytes | None:
    """Trả bytes PDF, hoặc None nếu không có/không tải được (paper không free)."""
    if not url:
        return None
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS)
    try:
        async with client.stream("GET", url) as r:
            if r.status_code != 200:
                return None
            ctype = r.headers.get("content-type", "").lower()
            if "pdf" not in ctype and not url.lower().endswith(".pdf"):
                return None  # thường là landing page HTML, không phải PDF
            buf = bytearray()
            async for part in r.aiter_bytes():
                buf.extend(part)
                if len(buf) > MAX_BYTES:
                    return None
            return bytes(buf) if buf[:5] == b"%PDF-" else None
    except (httpx.HTTPError, OSError):
        return None
    finally:
        if own:
            await client.aclose()
