"""Tiện ích audio dựa trên `pydub` — đo thời lượng, chèn khoảng lặng, nối file.

`pydub` tự nó gọi FFmpeg ĐỒNG BỘ (`subprocess.run` nội bộ), nên mọi hàm ở đây bọc
bằng `asyncio.to_thread()` để không chặn event loop (mục 4 `lms-ai-worker-rules`) dù
API bên ngoài vẫn là `async def`.

Dùng cho:
  · BR-DUB-03 — đo thời lượng thật sau khi Edge-TTS tổng hợp để tính hệ số R
  · BR-CHUNK-05 — ghép các câu trong 1 chunk (kèm khoảng lặng đúng vị trí) và ghép
    toàn bộ chunk thành `final.mp3`
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydub import AudioSegment


def _load(path: str | Path) -> AudioSegment:
    return AudioSegment.from_file(str(path))


async def measure_duration_sec(path: str | Path) -> float:
    def _measure() -> float:
        return len(_load(path)) / 1000.0

    return await asyncio.to_thread(_measure)


async def pad_silence(path: str | Path, pad_sec: float) -> None:
    """Chèn khoảng lặng vào CUỐI file — nhánh R ≤ 1.0 của BR-DUB-03."""
    if pad_sec <= 0:
        return

    def _pad() -> None:
        audio = _load(path)
        silence = AudioSegment.silent(duration=int(pad_sec * 1000), frame_rate=audio.frame_rate)
        (audio + silence).export(str(path), format="mp3")

    await asyncio.to_thread(_pad)


async def concat_with_leading_silence(
    segment_paths: list[str | Path],
    leading_silences_sec: list[float],
    out_path: str | Path,
) -> None:
    """Ghép các câu trong 1 chunk theo ĐÚNG mốc thời gian gốc.

    `leading_silences_sec[i]` là khoảng lặng chèn TRƯỚC `segment_paths[i]` — khoảng
    cách giữa câu trước và câu này trong transcript gốc, để bản lồng tiếng không bị
    dồn toa so với `T_orig` (BR-CHUNK-05).
    """
    if len(segment_paths) != len(leading_silences_sec):
        raise ValueError("segment_paths va leading_silences_sec phai cung do dai")

    def _concat() -> None:
        merged = AudioSegment.empty()
        for path, gap in zip(segment_paths, leading_silences_sec):
            if gap > 0:
                merged += AudioSegment.silent(duration=int(gap * 1000))
            merged += _load(path)
        merged.export(str(out_path), format="mp3")

    await asyncio.to_thread(_concat)


async def concat_files(paths: list[str | Path], out_path: str | Path) -> None:
    """Ghép danh sách file mp3 liên tiếp, không chèn khoảng lặng — dùng nối các chunk
    10 phút thành `final.mp3` (đã tự đúng mốc thời gian ở bước ghép từng chunk).
    """

    def _concat() -> None:
        merged = AudioSegment.empty()
        for path in paths:
            merged += _load(path)
        merged.export(str(out_path), format="mp3")

    await asyncio.to_thread(_concat)


async def extract_range(src_path: str | Path, start_sec: float, end_sec: float, out_path: str | Path) -> None:
    """Cắt một đoạn [start_sec, end_sec) — dùng khi giữ audio GỐC cho chunk lỗi
    (BR-CHUNK-04: "chunk lỗi giữ audio gốc riêng đoạn đó").
    """

    def _extract() -> None:
        audio = _load(src_path)
        clip = audio[int(start_sec * 1000):int(end_sec * 1000)]
        clip.export(str(out_path), format="mp3")

    await asyncio.to_thread(_extract)
