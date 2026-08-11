"""Anti-corruption layer cho mọi dịch vụ AI bên ngoài.

Nguyên tắc (xem `lms-ai-worker-rules` mục 5):

1. **Bulkhead** — mỗi provider có `httpx.AsyncClient` RIÊNG với timeout/limits riêng.
   Không bao giờ dùng chung một client toàn cục: Gemini chậm không được làm cạn
   connection pool mà Edge-TTS đang cần.

2. **Kiểu trả về tường minh** — provider trả dataclass hoặc raise `ProviderError`,
   TUYỆT ĐỐI không trả `dict` thô hay để lộ exception của thư viện ra ngoài. Nhờ vậy
   tầng retry (BR-CHUNK-04) quyết định được `retryable` mà không cần biết chi tiết
   nội bộ của Groq/Gemini/Edge-TTS.

3. **Đóng client khi shutdown** — trong FastAPI `lifespan`, không phải `atexit`.
"""

from __future__ import annotations

import httpx


class ProviderError(Exception):
    """Lỗi từ một dịch vụ ngoài, đã được chuẩn hoá.

    `retryable` là thông tin quan trọng nhất: tầng gọi dùng nó để quyết định có đưa
    vào vòng retry (tối đa 3 lần, exponential backoff — BR-CHUNK-04) hay dừng luôn.
    """

    def __init__(self, message: str, *, retryable: bool, code: str | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.code = code

    def __repr__(self) -> str:  # pragma: no cover - chỉ để log dễ đọc
        return f"ProviderError(code={self.code!r}, retryable={self.retryable}, msg={self!s})"


class ProviderTimeout(ProviderError):
    """Hết thời gian chờ — luôn có thể retry."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True, code="timeout")


class ProviderRateLimited(ProviderError):
    """Bị dịch vụ ngoài giới hạn tần suất — retry được nhưng cần chờ lâu hơn."""

    def __init__(self, message: str, *, retry_after_sec: int | None = None) -> None:
        super().__init__(message, retryable=True, code="rate_limited")
        self.retry_after_sec = retry_after_sec


class ProviderInvalidResponse(ProviderError):
    """Dịch vụ trả về dữ liệu không đúng định dạng mong đợi — retry vô nghĩa."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False, code="invalid_response")


def build_client(
    base_url: str,
    *,
    connect: float = 5.0,
    read: float = 60.0,
    write: float = 10.0,
    pool: float = 5.0,
    max_connections: int = 20,
    max_keepalive: int = 10,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Tạo một AsyncClient riêng cho MỘT provider (bulkhead).

    Giá trị `read` mặc định 60s vì gọi LLM/STT thường lâu; các provider cần lâu hơn
    thì tự truyền vào khi khởi tạo.
    """
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(connect=connect, read=read, write=write, pool=pool),
        limits=httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
        ),
        headers=headers or {},
    )


def map_http_error(exc: Exception) -> ProviderError:
    """Chuyển exception của httpx thành ProviderError đã chuẩn hoá."""
    if isinstance(exc, httpx.TimeoutException):
        return ProviderTimeout(str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            retry_after = exc.response.headers.get("retry-after")
            return ProviderRateLimited(
                str(exc),
                retry_after_sec=int(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        # 5xx là lỗi phía dịch vụ -> retry được; 4xx còn lại là lỗi request của mình
        return ProviderError(str(exc), retryable=status >= 500, code=f"http_{status}")
    if isinstance(exc, httpx.HTTPError):
        return ProviderError(str(exc), retryable=True, code="network")
    return ProviderError(str(exc), retryable=False, code="unknown")
