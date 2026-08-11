"""Kiểu dữ liệu dùng chung xuyên suốt pipeline lồng tiếng (F5.2).

Thống nhất một dạng "câu thoại" duy nhất bất kể nguồn gốc — ASR mới bóc băng
(`groq_asr.SttSegment`, mốc thời gian TƯƠNG ĐỐI trong chunk) hay tái sử dụng từ
transcript gốc đã có (`backend_client.SourceSegment`, mốc thời gian TUYỆT ĐỐI toàn
bài) — để `translation.py`/`dubbing_service.py` không phải phân nhánh theo nguồn.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """Một câu thoại, mốc thời gian TUYỆT ĐỐI tính từ đầu bài học (giây)."""

    seq: int
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start
