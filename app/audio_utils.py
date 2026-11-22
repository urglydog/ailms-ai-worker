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
import logging
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
    durations_sec: list[float] | None = None,
) -> TimelineResult:
    """Chọn cách ghép theo `TIMELINE_ENGINE` ("ffmpeg" | "pydub"); 2 cách cho cùng kết quả (BR-CHUNK-05).
    "ffmpeg" lỗi thì tự quay về "pydub" — không bao giờ làm hỏng chunk vì đổi cách ghép."""
    from app.config import settings

    if settings.timeline_engine == "ffmpeg":
        try:
            return await place_on_timeline_ffmpeg(
                segment_paths, desired_onsets_sec, chunk_len_sec, out_path, durations_sec,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("Ghep bang 1 lenh FFmpeg that bai, dung cach cu (pydub): %s", exc)
    return await place_on_timeline_pydub(segment_paths, desired_onsets_sec, chunk_len_sec, out_path)


async def probe_audio(path: str | Path) -> tuple[float, int]:
    """(độ dài giây, sample rate) đọc từ header bằng ffprobe — không giải mã cả file."""
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate:format=duration", "-of", "default=noprint_wrappers=1", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe that bai ({path}): {err.decode(errors='ignore')[-300:]}")
    fields = dict(line.split("=", 1) for line in out.decode().splitlines() if "=" in line)
    return float(fields["duration"]), int(fields.get("sample_rate", 0) or 0)


_PROBE_CONCURRENCY = 8


async def place_on_timeline_ffmpeg(
    segment_paths: list[str | Path],
    desired_onsets_sec: list[float],
    chunk_len_sec: float,
    out_path: str | Path,
    durations_sec: list[float] | None = None,
) -> TimelineResult:
    """Cùng thuật toán với `place_on_timeline_pydub` (mốc tuyệt đối -> tăng tốc cả đoạn tối đa
    `MAX_CHUNK_TEMPO` -> cắt/đệm đúng độ dài chunk), nhưng dựng bằng MỘT lệnh FFmpeg (22/11/2026).

    Cách cũ: mỗi câu pydub mở 1 tiến trình FFmpeg để giải mã (tuần tự, ~0,2 s/câu) rồi nối trong
    Python (mỗi lần nối chép lại cả đoạn). Cách mới: tính mốc bằng đúng `plan_onsets`, rồi 1 lượt
    FFmpeg nối [lặng, câu, lặng, câu, ...] (các câu không bao giờ chồng nhau nên chỉ cần NỐI), tăng
    tốc và khớp độ dài trong cùng lượt.

    Độ dài câu: dùng `durations_sec` caller đã đo sẵn lúc TTS (chính xác). KHÔNG dùng độ dài trong
    header MP3 (ffprobe) — nó dư ~35–45 ms/câu vì tính cả phần đệm của bộ mã hoá, cộng dồn qua 190
    câu sẽ lệch vài giây. Không có `durations_sec` thì giải mã song song để đo. Ngoài ra mỗi câu
    được đệm/cắt về ĐÚNG ô thời gian của nó, nên sai số nhỏ không bao giờ dồn sang câu sau.
    """
    if len(segment_paths) != len(desired_onsets_sec):
        raise ValueError("segment_paths va desired_onsets_sec phai cung do dai")
    if not segment_paths:
        raise ValueError("khong co cau nao de ghep")

    sem = asyncio.Semaphore(_PROBE_CONCURRENCY)

    async def probe(p: str | Path) -> tuple[float, int]:
        async with sem:
            return await probe_audio(p)

    if durations_sec is not None and len(durations_sec) == len(segment_paths):
        durations = [max(0.0, float(d)) for d in durations_sec]
    else:
        async def measure(p: str | Path) -> float:
            async with sem:
                return await measure_duration_sec(p)

        durations = list(await asyncio.gather(*(measure(p) for p in segment_paths)))
    sample_rate = (await probe(segment_paths[0]))[1] or 16000
    onsets = plan_onsets(desired_onsets_sec, durations)
    max_delay = max((on - max(0.0, want) for on, want in zip(onsets, desired_onsets_sec)), default=0.0)
    raw_len = onsets[-1] + durations[-1]

    tempo = 1.0
    if raw_len > chunk_len_sec + 0.05 and chunk_len_sec > 0:
        tempo = min(raw_len / chunk_len_sec, MAX_CHUNK_TEMPO)

    fmt = f"aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=mono"
    parts: list[str] = []
    labels: list[str] = []
    cursor = 0.0
    for i, (onset, dur) in enumerate(zip(onsets, durations)):
        gap = onset - cursor
        if gap > 0.0005:
            parts.append(f"anullsrc=r={sample_rate}:cl=mono,atrim=duration={gap:.6f},{fmt}[g{i}]")
            labels.append(f"[g{i}]")
        # đệm/cắt câu về đúng `dur` -> vị trí các câu sau không phụ thuộc độ dài giải mã thực tế
        parts.append(f"[{i}:a]{fmt},apad=whole_dur={dur:.6f},atrim=end={dur:.6f}[s{i}]")
        labels.append(f"[s{i}]")
        cursor = onset + dur
    chain = f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1"
    if tempo > 1.0:
        chain += f",atempo={tempo:.4f}"
    chain += f",apad=whole_dur={chunk_len_sec:.6f},atrim=end={chunk_len_sec:.6f}[out]"
    parts.append(chain)

    script = Path(str(out_path) + ".filter.txt")
    script.write_text(";\n".join(parts), encoding="utf-8")
    try:
        inputs: list[str] = []
        for p in segment_paths:
            inputs += ["-i", str(p)]
        await _ffmpeg(*inputs, "-/filter_complex", str(script), "-map", "[out]", str(out_path))
    finally:
        script.unlink(missing_ok=True)

    # Đã apad + atrim về đúng chunk_len trong cùng lượt; KHÔNG đọc lại độ dài từ header MP3 (dư ~0,09 s
    # do phần đệm của bộ mã hoá — độ dài giải mã thật đúng bằng chunk_len, xem SoSanh_GhepChunk.md).
    return TimelineResult(
        raw_length_sec=round(raw_len, 3),
        final_length_sec=round(chunk_len_sec, 3),
        max_delay_sec=round(max_delay, 3),
        tempo_applied=round(tempo, 4),
    )


async def place_on_timeline_pydub(
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


async def write_silence(path: str | Path, duration_sec: float) -> None:
    """Ghi 1 file mp3 im lặng — thay cho câu không có chữ để đọc (vd chỉ có dấu câu)."""

    def _write() -> None:
        AudioSegment.silent(duration=int(duration_sec * 1000)).export(str(path), format="mp3")

    await asyncio.to_thread(_write)


async def change_tempo(path: str | Path, factor: float) -> None:
    """Tăng tốc 1 file câu tại chỗ bằng FFmpeg `atempo` (giữ cao độ giọng).

    Thay cho việc gọi lại Azure TTS chỉ để đổi `rate` (hiệu năng dubbing, S2): đã có file và đã đo
    độ dài ở lần tổng hợp đầu, nên tăng tốc cục bộ — không tốn thêm request lẫn ký tự TTS.
    """
    if factor <= 1.0:
        return
    src = Path(path)
    tmp = src.with_name(src.stem + "_tempo" + src.suffix)
    await _ffmpeg("-i", str(src), "-filter:a", f"atempo={factor:.4f}", str(tmp))
    tmp.replace(src)


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
