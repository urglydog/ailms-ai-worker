"""Tải audio gốc của bài học KHI CẦN, không tải sẵn (tối ưu B, 22/11/2026).

Lồng tiếng bài đã có bản ký âm (ngôn ngữ thứ 2 trở đi) mà nhạc nền cũng đã có trên B2 thì pipeline
KHÔNG cần audio gốc: không chạy ASR, không tách nhạc. Trước đây vẫn tải lại từ YouTube mỗi job —
trên server phải đi qua proxy, chậm và dễ bị YouTube chặn. Giờ chỉ tải khi một bước thật sự cần
(chunk lỗi phải giữ audio gốc, chunk không có câu nào, hoặc phải tách nhạc).

Đăng ký theo đường dẫn file (`register`), các bước cần audio gọi `await ensure(path)`: file đã có
thì trả về ngay, chưa có thì tải đúng 1 lần (có khoá, nhiều bước gọi cùng lúc vẫn chỉ tải 1 lần).
Đường dẫn chưa đăng ký -> coi như file đã có sẵn (giữ hành vi cũ, ví dụ trong test).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path


class SourceUnavailableError(Exception):
    """BR-DUB-11 — nguồn video (URL B2 hoặc YouTube) không còn truy cập được."""


class _LazySource:
    def __init__(self, path: Path, download: Callable[[Path], Awaitable[None]]):
        self.path = path
        self._download = download
        self._lock = asyncio.Lock()
        self.downloaded = False

    async def ensure(self) -> Path:
        async with self._lock:
            if not self.downloaded:
                try:
                    await self._download(self.path)
                except Exception as exc:  # BR-DUB-11 — mọi lỗi tải/tách đều là nguồn không khả dụng
                    raise SourceUnavailableError(str(exc)) from exc
                self.downloaded = True
        return self.path


_registry: dict[str, _LazySource] = {}


def register(path: Path, download: Callable[[Path], Awaitable[None]]) -> None:
    _registry[str(path)] = _LazySource(path, download)


def unregister(path: Path) -> None:
    _registry.pop(str(path), None)


def was_downloaded(path: Path) -> bool:
    src = _registry.get(str(path))
    return src.downloaded if src else True


async def ensure(path: str | Path) -> Path:
    src = _registry.get(str(path))
    return await src.ensure() if src else Path(path)
