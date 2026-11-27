"""So sánh 2 cách ghép câu thành chunk (pydub cũ vs 1 lệnh FFmpeg) trên dữ liệu giống thật.

Chạy trong container worker:
    python scripts/bench_timeline.py <file audio có lời nói> [--repeat 3]

Dữ liệu giả lập đúng như pipeline tạo ra:
  · cắt audio có lời thành N câu dài 1,5–4,5 s, mã hoá giống Azure (MP3 16 kHz mono 32 kbps);
  · ~20% câu được tăng tốc bằng `change_tempo` (giống câu dài hơn khung);
  · mốc mong muốn cách nhau 0,2–1,2 s, có câu tràn sang câu sau (để thử `plan_onsets`);
  · 3 cỡ: 63 câu/376 s (bài 6 phút), 122 câu/566 s (bài 9,4 phút), 190 câu/600 s (chunk 10 phút đầy).
Đo: thời gian ghép, độ dài file ra, độ trễ tối đa, hệ số tăng tốc, và độ khớp nội dung giữa 2 file
(vị trí bắt đầu có tiếng + độ tương quan tín hiệu) để chắc cách mới không đổi kết quả.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import tempfile
import time
from pathlib import Path

from pydub import AudioSegment

from app import audio_utils

# (số câu, độ dài chunk) — ca cuối nhét 190 câu vào 480 s để chunk bị TRÀN -> thử nhánh tăng tốc cả đoạn
CASES = [(63, 376.0), (122, 566.0), (190, 600.0), (190, 480.0)]


def make_sentences(source: AudioSegment, n: int, chunk_len: float, work: Path, seed: int):
    rnd = random.Random(seed)
    paths, onsets, durations = [], [], []
    cursor = 0.0
    src_ms = len(source)
    for i in range(n):
        dur = rnd.uniform(1.5, 4.5)
        start_ms = rnd.randint(0, max(0, src_ms - int(dur * 1000) - 1))
        clip = source[start_ms:start_ms + int(dur * 1000)].set_frame_rate(16000).set_channels(1)
        p = work / f"s{i}.mp3"
        clip.export(str(p), format="mp3", bitrate="32k")
        paths.append(p)
        onsets.append(cursor)
        # khoảng cách tới câu sau: thường 0,2–1,2 s, đôi khi âm (câu tràn) để thử plan_onsets
        cursor += dur * rnd.uniform(0.85, 1.0) + rnd.uniform(-0.3, 1.2)
        cursor = max(cursor, onsets[-1] + 0.3)
    # co giãn mốc cho vừa chunk (giống bài thật: lời nói phủ gần hết chunk)
    fill = 0.97 if chunk_len >= 0.6 * 3.0 * n else 0.80   # ca tràn: mốc dồn sát nhau hơn
    scale = (chunk_len * fill) / cursor
    onsets = [o * scale for o in onsets]
    return paths, onsets, rnd


async def prepare(source: AudioSegment, n: int, chunk_len: float, work: Path, seed: int):
    paths, onsets, rnd = make_sentences(source, n, chunk_len, work, seed)
    for p in paths:
        if rnd.random() < 0.2:
            await audio_utils.change_tempo(p, rnd.uniform(1.05, 1.3))
    durations = [await audio_utils.measure_duration_sec(p) for p in paths]   # giống duration_sec từ TTS
    return paths, onsets, durations


_SR = 8000


def _pcm(audio: AudioSegment):
    import numpy as np

    return np.array(audio.set_frame_rate(_SR).set_channels(1).get_array_of_samples(), dtype=float)


def envelope_correlation(a: AudioSegment, b: AudioSegment, win_ms: int = 20) -> float:
    """Tương quan ĐƯỜNG BAO âm lượng (RMS mỗi 20 ms) giữa 2 file — so 'tiếng ở đâu, to bao nhiêu'.
    Không so dạng sóng từng mẫu: mã hoá MP3 lại làm lệch pha nên dạng sóng khác dù nghe y hệt."""
    import numpy as np

    x, y = _pcm(a), _pcm(b)
    w = _SR * win_ms // 1000
    n = min(len(x), len(y)) // w * w
    ex = np.sqrt((x[:n].reshape(-1, w) ** 2).mean(axis=1))
    ey = np.sqrt((y[:n].reshape(-1, w) ** 2).mean(axis=1))
    ex, ey = ex - ex.mean(), ey - ey.mean()
    return float(ex @ ey / ((np.linalg.norm(ex) * np.linalg.norm(ey)) or 1.0))


def sentence_offsets_ms(out: AudioSegment, clips: list[AudioSegment], planned: list[float]) -> list[float]:
    """Với mỗi câu: lệch bao nhiêu ms so với mốc đã tính (tìm trong ±300 ms, bước 5 ms)."""
    import numpy as np

    y = _pcm(out)
    found = []
    for clip, onset in zip(clips, planned):
        c = _pcm(clip)[: _SR * 2]                 # 2 s đầu của câu là đủ để định vị
        c = c - c.mean()
        s = int(onset * _SR)
        best, best_lag = -2.0, 0
        for lag in range(-_SR * 3 // 10, _SR * 3 // 10 + 1, _SR // 200):
            a = s + lag
            if a < 0 or a + len(c) > len(y):
                continue
            seg = y[a:a + len(c)] - y[a:a + len(c)].mean()
            d = np.linalg.norm(seg) * np.linalg.norm(c)
            r = float(seg @ c / d) if d else 0.0
            if r > best:
                best, best_lag = r, lag
        found.append(abs(best_lag) / _SR * 1000)
    return found


async def main(source_path: str, repeat: int) -> None:
    source = AudioSegment.from_file(source_path)
    print(f"| Cỡ | Cách | Thời gian ghép (trung bình {repeat} lần) | Độ dài ra | Trễ tối đa | Tăng tốc |")
    print("|---|---|---|---|---|---|")
    checks = []
    for n, chunk_len in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            paths, onsets, durations = await prepare(source, n, chunk_len, work, seed=n)
            outs = {}
            for name, fn, kwargs in (
                ("pydub (cũ)", audio_utils.place_on_timeline_pydub, {}),
                ("ffmpeg (mới)", audio_utils.place_on_timeline_ffmpeg, {"durations_sec": durations}),
            ):
                times = []
                for r in range(repeat):
                    out = work / f"{name[:5]}_{r}.mp3"
                    t0 = time.monotonic()
                    res = await fn(paths, onsets, chunk_len, out, **kwargs)
                    times.append(time.monotonic() - t0)
                outs[name] = (out, res)
                print(f"| {n} câu / {chunk_len:.0f} s | {name} | {statistics.mean(times):.2f} s "
                      f"(min {min(times):.2f}) | {res.final_length_sec:.2f} s | {res.max_delay_sec:.2f} s "
                      f"| x{res.tempo_applied} |")
            (pa, ra), (pb, rb) = outs.values()
            a, b = AudioSegment.from_file(pa), AudioSegment.from_file(pb)
            planned = audio_utils.plan_onsets(onsets, durations)
            clips = [AudioSegment.from_file(p) for p in paths]
            la = sentence_offsets_ms(a, clips, planned)
            lb = sentence_offsets_ms(b, clips, planned)
            checks.append((n, len(a) / 1000, len(b) / 1000, max(la), max(lb), envelope_correlation(a, b)))
    print()
    print("| Cỡ | Độ dài pydub | Độ dài ffmpeg | Câu lệch mốc nhiều nhất: pydub | ffmpeg | Tương quan đường bao âm lượng |")
    print("|---|---|---|---|---|---|")
    for n, len_a, len_b, worst_a, worst_b, env in checks:
        print(f"| {n} câu | {len_a:.3f} s | {len_b:.3f} s | {worst_a:.0f} ms | {worst_b:.0f} ms | {env:.4f} |")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(main(args.source, args.repeat))
