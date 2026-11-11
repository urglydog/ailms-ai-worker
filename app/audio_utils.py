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
from dataclasses import dataclass
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


MAX_CHUNK_TEMPO = 1.15   # tăng tốc tối đa CẢ đoạn khi cuối đoạn vẫn dài hơn khung


@dataclass(frozen=True)
class TimelineResult:
    """Thống kê sau khi xếp câu lên trục thời gian của 1 chunk (dùng cho log/đo đạc)."""

    raw_length_sec: float      # độ dài trước khi khớp về khung chunk
    final_length_sec: float    # độ dài file xuất ra
    max_delay_sec: float       # câu bị lùi nhiều nhất so với mốc gốc
    tempo_applied: float       # hệ số tăng tốc cả đoạn (1.0 = không đổi)


def plan_onsets(desired_onsets_sec: list[float], durations_sec: list[float]) -> list[float]:
    """Xếp câu theo MỐC TUYỆT ĐỐI trong chunk (BR-CHUNK-05, sửa 11/11/2026).

    onset_i = max(mốc gốc_i, thời điểm câu i-1 kết thúc)

    Câu nào dài hơn khung chỉ lấn vào khoảng lặng phía sau; câu sau bị lùi lại nhưng
    KHÔNG BAO GIỜ chồng lên câu trước, và ngay khi gặp khoảng lặng đủ dài thì câu sau
    quay về đúng mốc gốc — độ trễ không cộng dồn suốt cả bài như cách cũ
    (`khoảng lặng = start_i − end_{i-1}` cố định).
    """
    onsets: list[float] = []
    cursor = 0.0
    for desired, dur in zip(desired_onsets_sec, durations_sec):
        onset = max(max(0.0, desired), cursor)
        onsets.append(onset)
        cursor = onset + max(0.0, dur)
    return onsets


async def place_on_timeline(
    segment_paths: list[str | Path],
    desired_onsets_sec: list[float],
    chunk_len_sec: float,
    out_path: str | Path,
) -> TimelineResult:
    """Ghép câu của 1 chunk theo mốc tuyệt đối và khớp đúng độ dài `chunk_len_sec`.

    - Thiếu: đệm lặng tới hết chunk.
    - Thừa (đoạn dày lời, không đủ khoảng lặng để bù): tăng tốc cả đoạn bằng FFmpeg
      `atempo` (giữ cao độ), tối đa `MAX_CHUNK_TEMPO`; phần còn dư sau đó mới cắt bỏ để
      chunk sau luôn bắt đầu đúng giờ — trễ không lan sang chunk kế tiếp.
    """
    if len(segment_paths) != len(desired_onsets_sec):
        raise ValueError("segment_paths va desired_onsets_sec phai cung do dai")

    def _build() -> tuple[AudioSegment, float]:
        clips = [_load(p) for p in segment_paths]
        onsets = plan_onsets(desired_onsets_sec, [len(c) / 1000.0 for c in clips])
        merged = AudioSegment.empty()
        max_delay = 0.0
        for clip, onset, desired in zip(clips, onsets, desired_onsets_sec):
            gap_ms = int(round(onset * 1000)) - len(merged)
            if gap_ms > 0:
                merged += AudioSegment.silent(duration=gap_ms, frame_rate=clip.frame_rate)
            merged += clip
            max_delay = max(max_delay, onset - max(0.0, desired))
        return merged, max_delay

    merged, max_delay = await asyncio.to_thread(_build)
    raw_len = len(merged) / 1000.0
    target_ms = int(round(chunk_len_sec * 1000))
    tempo = 1.0

    if raw_len > chunk_len_sec + 0.05 and chunk_len_sec > 0:
        tempo = min(raw_len / chunk_len_sec, MAX_CHUNK_TEMPO)
        tmp_in = Path(str(out_path) + ".raw.wav")
        tmp_out = Path(str(out_path) + ".tempo.wav")
        await asyncio.to_thread(merged.export, str(tmp_in), format="wav")
        await _ffmpeg("-i", str(tmp_in), "-filter:a", f"atempo={tempo:.4f}", str(tmp_out))
        merged = await asyncio.to_thread(_load, tmp_out)
        tmp_in.unlink(missing_ok=True)
        tmp_out.unlink(missing_ok=True)

    def _fit_and_export() -> int:
        audio = merged
        if len(audio) < target_ms:
            audio += AudioSegment.silent(duration=target_ms - len(audio), frame_rate=audio.frame_rate)
        elif len(audio) > target_ms:
            audio = audio[:target_ms]
        audio.export(str(out_path), format="mp3")
        return len(audio)

    final_ms = await asyncio.to_thread(_fit_and_export)
    return TimelineResult(
        raw_length_sec=round(raw_len, 3),
        final_length_sec=final_ms / 1000.0,
        max_delay_sec=round(max_delay, 3),
        tempo_applied=round(tempo, 4),
    )


async def _ffmpeg(*args: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg atempo that bai: {stderr.decode(errors='ignore')[-500:]}")


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
