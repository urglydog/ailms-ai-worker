"""Che khóa/token trong log (21/11/2026) — lớp phòng thủ thứ hai sau khi đã chuyển khóa Gemini sang header `x-goog-api-key`.

Lý do: `httpx` ghi INFO nguyên URL của mỗi request; khi khóa nằm trong URL (`?key=...`) thì MỖI lệnh gọi in đủ khóa ra log (từng xảy ra). Bộ lọc này che mọi giá trị
`key=`/`api_key=`/`token=` trong URL và các chuỗi trông như khóa Google (`AIza…`, `AQ.…`) ở log của `httpx`/`httpcore`, để dù sau này ai đó lỡ đưa khóa vào URL thì log vẫn sạch.
"""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    re.compile(r"(?i)([?&](?:key|api[_-]?key|apikey|access[_-]?token|token)=)[^&\s\"']+"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bAQ\.[0-9A-Za-z_\-]{20,}"),
]
_MASK = "<redacted>"


def redact(text: str) -> str:
    """Che giá trị khóa trong một chuỗi (URL hoặc thông điệp log)."""
    out = _PATTERNS[0].sub(lambda m: m.group(1) + _MASK, text)
    for rx in _PATTERNS[1:]:
        out = rx.sub(_MASK, out)
    return out


class RedactSecretsFilter(logging.Filter):
    """Định dạng thông điệp rồi che khóa trước khi ghi; không bao giờ làm mất bản ghi log."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            cleaned = redact(message)
            if cleaned != message:
                record.msg = cleaned
                record.args = ()
        except Exception:  # noqa: BLE001 — log không được làm hỏng luồng chính
            pass
        return True


_INSTALLED = False


def install() -> None:
    """Gắn bộ lọc vào logger của thư viện HTTP (idempotent)."""
    global _INSTALLED
    if _INSTALLED:
        return
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).addFilter(RedactSecretsFilter())
    _INSTALLED = True
