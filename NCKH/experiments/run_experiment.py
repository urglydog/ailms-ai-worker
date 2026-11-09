"""Thực nghiệm cho bài báo SSRC: so sánh 4 phương án đồng bộ thời lượng lồng tiếng.

Script này KHÔNG sửa code của pipeline, KHÔNG ghi vào database, KHÔNG gọi backend.
Nó import trực tiếp các hàm có sẵn trong `app/` (Whisper/Groq, Gemini, Azure TTS,
Adaptive Speech Rate) rồi ghi kết quả từng câu ra CSV.

Bốn phương án (khớp Bảng "tab:results" trong NCKH/paper/main.tex):
  V1  one_pass_default   : dịch 1 pha (sát nghĩa), TTS tốc độ mặc định, không điều chỉnh
  V2  two_pass_default   : dịch 2 pha (thêm biên tập theo ngân sách thời lượng), TTS mặc định
  V3  two_pass_speedup   : V2 + tăng tốc độ đọc tối đa +30%, KHÔNG rút gọn bằng LLM
  V4  proposed           : V2 + Adaptive Speech Rate đầy đủ (gọi đúng hàm của pipeline)

Để công bằng và tiết kiệm API:
  - ASR chạy 1 lần / video, lưu cache JSON (lần chạy sau không gọi lại Groq).
  - 2 lời gọi Gemini của pha dịch dùng chung: kết quả pha 1 cho V1, kết quả pha 2 cho V2-V4.
  - TTS ở tốc độ mặc định của bản dịch pha 2 dùng chung cho V2 và V3.

Cách chạy (đứng ở thư mục project/ai-worker để nạp đúng file .env):
    python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json
    python NCKH/experiments/run_experiment.py --manifest ... --variants V1,V4 --max-chunks 1

Đầu ra (mặc định NCKH/experiments/results/<run_id>/):
    segments.csv   — 1 dòng / câu / phương án
    videos.csv     — 1 dòng / video: thời gian từng giai đoạn, số lần gọi API
    run_meta.json  — cấu hình, model, thời điểm chạy (ghi vào mục Thiết lập thực nghiệm)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

AI_WORKER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_WORKER_ROOT))

from app import audio_utils, media  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import Segment  # noqa: E402
from app.providers import azure_tts, gemini, groq_asr  # noqa: E402
from app.services import dubbing_service, translation  # noqa: E402

R_MIN = float(dubbing_service.R_LOWER_BOUND)   # 1.0
R_MAX = float(dubbing_service.R_UPPER_BOUND)   # 1.3
ALL_VARIANTS = ["V1", "V2", "V3", "V4"]


# ---------------------------------------------------------------------------
# Đếm số lần gọi API (bọc hàm gốc, không sửa code pipeline)
# ---------------------------------------------------------------------------
@dataclass
class CallCounter:
    llm: int = 0
    tts: int = 0
    resummarize: int = 0

    def reset(self) -> "CallCounter":
        snap = CallCounter(self.llm, self.tts, self.resummarize)
        self.llm = self.tts = self.resummarize = 0
        return snap


COUNTER = CallCounter()
_orig_generate = gemini.generate
_orig_synthesize = azure_tts.synthesize
_orig_resummarize = translation.resummarize


async def _counted_generate(*args, **kwargs):
    COUNTER.llm += 1
    return await _orig_generate(*args, **kwargs)


async def _counted_synthesize(*args, **kwargs):
    COUNTER.tts += 1
    return await _orig_synthesize(*args, **kwargs)


async def _counted_resummarize(*args, **kwargs):
    COUNTER.resummarize += 1
    return await _orig_resummarize(*args, **kwargs)


def install_counters() -> None:
    # translation.py gọi `gemini.generate` qua module, dubbing_service gọi
    # `azure_tts.synthesize` và `translation.resummarize` qua module -> vá ở module là đủ.
    gemini.generate = _counted_generate
    azure_tts.synthesize = _counted_synthesize
    translation.resummarize = _counted_resummarize


# ---------------------------------------------------------------------------
# Dữ liệu
# ---------------------------------------------------------------------------
@dataclass
class VideoSpec:
    id: str
    source: str                 # đường dẫn file local, URL https (mp4) hoặc URL YouTube
    target_language: str = "vi-VN"
    voice_name: str = "vi-VN-HoaiMyNeural"
    category: str = ""          # "CNTT" / "KyNangMem" — để thống kê theo nhóm
    note: str = ""


@dataclass
class SegmentRow:
    run_id: str
    video_id: str
    category: str
    variant: str
    chunk_index: int
    seq: int
    t_orig: float
    src_text: str
    tgt_text: str
    tgt_chars: int
    t_tts_default: float        # thời lượng TTS ở +0% (trước khi điều chỉnh)
    r_default: float            # R = t_tts_default / t_orig
    branch: str                 # pad | speedup | summarize | capped | none
    applied_rate: float         # hệ số tốc độ cuối (1.00 = mặc định, 1.30 = +30%)
    n_resummarize: int
    was_summarized: bool
    t_final: float              # thời lượng audio cuối của câu
    overrun: float              # max(0, t_final - t_orig): phần tràn sang câu sau
    abs_delta: float            # |t_final - t_orig|
    llm_calls: int              # lời gọi LLM phát sinh RIÊNG cho câu này (rút gọn)
    tts_calls: int


@dataclass
class VideoRow:
    run_id: str
    video_id: str
    category: str
    duration_sec: float
    n_chunks: int
    n_segments: int
    speech_ratio: float
    t_prepare_sec: float
    t_asr_sec: float
    asr_cached: bool
    t_translate_sec: float
    t_tts_default_sec: float
    t_v3_sec: float
    t_v4_sec: float
    llm_calls_translate: int
    tts_calls_total: int
    resummarize_calls_v4: int
    timings: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Bước chuẩn bị: lấy audio, chia chunk, ASR (có cache)
# ---------------------------------------------------------------------------
async def prepare_audio(spec: VideoSpec, work: Path) -> Path:
    out = work / "source.wav"
    if out.exists():
        return out
    src = spec.source
    if "youtube.com" in src or "youtu.be" in src:
        await media.download_youtube_audio(src, out)
    elif src.startswith("http"):
        await media.extract_audio_from_url(src, out)
    else:
        await media.extract_audio_from_url(str(Path(src).resolve()), out)  # ffmpeg đọc được file local
    return out


async def transcribe_cached(spec: VideoSpec, audio: Path, work: Path, max_chunks: int | None):
    """Trả về (danh sách chunk, {chunk_index: [Segment]}, ngôn ngữ nguồn, cached?)."""
    duration = await media.probe_duration_sec(audio)
    chunks = dubbing_service.split_into_chunks(int(duration), settings.chunk_minutes)
    if max_chunks:
        chunks = chunks[:max_chunks]

    cache = work / "asr_cache.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("chunk_minutes") == settings.chunk_minutes and len(data["chunks"]) >= len(chunks):
            segs = {
                int(k): [Segment(**s) for s in v] for k, v in data["chunks"].items() if int(k) < len(chunks)
            }
            return duration, chunks, segs, data["language"], True

    segs: dict[int, list[Segment]] = {}
    language = ""
    seq = 1
    for ch in chunks:
        wav = work / f"chunk_{ch.index}.wav"
        await audio_utils.extract_range(audio, ch.start_sec, ch.end_sec, wav)
        stt = await groq_asr.transcribe(str(wav))
        language = language or stt.language
        segs[ch.index] = []
        for s in stt.segments:
            segs[ch.index].append(Segment(seq=seq, start=ch.start_sec + s.start, end=ch.start_sec + s.end, text=s.text))
            seq += 1
    cache.write_text(json.dumps({
        "chunk_minutes": settings.chunk_minutes,
        "language": language,
        "chunks": {str(k): [asdict(s) for s in v] for k, v in segs.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return duration, chunks, segs, language, False


# ---------------------------------------------------------------------------
# Dịch: tách 2 pha để lấy được cả kết quả pha 1 (V1) và pha 2 (V2-V4)
# ---------------------------------------------------------------------------
async def translate_two_phase(segments: list[Segment], src_lang: str, tgt_lang: str) -> tuple[list[str], list[str]]:
    """Sao chép đúng logic `translation.translate_batch` nhưng trả về CẢ HAI pha.
    Dùng chung prompt builder của pipeline nên prompt giống hệt khi chạy thật.
    """
    if not segments:
        return [], []
    numbered = {str(i + 1): s.text for i, s in enumerate(segments)}
    direct = translation._extract_json(
        (await gemini.generate(translation._build_direct_prompt(numbered, src_lang, tgt_lang))).text
    )
    durations = {str(i + 1): s.duration for i, s in enumerate(segments)}
    adapt = translation._extract_json(
        (await gemini.generate(translation._build_adapt_prompt(direct, durations, tgt_lang))).text
    )
    one = [(direct.get(str(i + 1)) or "").strip() for i in range(len(segments))]
    two = [(adapt.get(str(i + 1)) or direct.get(str(i + 1)) or "").strip() for i in range(len(segments))]
    return one, two


# ---------------------------------------------------------------------------
# Các phương án
# ---------------------------------------------------------------------------
def _row(base: dict, **kw) -> SegmentRow:
    t_orig = base["t_orig"]
    t_final = kw["t_final"]
    return SegmentRow(
        **base, **kw,
        overrun=round(max(0.0, t_final - t_orig), 3),
        abs_delta=round(abs(t_final - t_orig), 3),
    )


def _default_row(base: dict, variant: str, text: str, t_tts: float) -> SegmentRow:
    """V1/V2: phát nguyên tốc độ; câu ngắn hơn khung thì được đệm lặng (như pipeline)."""
    r = t_tts / base["t_orig"] if base["t_orig"] > 0 else 0.0
    t_final = max(t_tts, base["t_orig"])
    return _row({**base, "variant": variant, "tgt_text": text, "tgt_chars": len(text),
                 "t_tts_default": round(t_tts, 3), "r_default": round(r, 3)},
                branch="pad" if r <= R_MIN else "none", applied_rate=1.0, n_resummarize=0,
                was_summarized=False, t_final=round(t_final, 3), llm_calls=0, tts_calls=1)


async def run_v3(base: dict, text: str, t_tts: float, voice: str, out: Path) -> SegmentRow:
    """Chỉ tăng tốc (trần +30%), không rút gọn."""
    t_orig = base["t_orig"]
    r = t_tts / t_orig if t_orig > 0 else 0.0
    tts_calls = 0
    if r <= R_MIN:
        branch, rate, t_final = "pad", 1.0, t_orig
    else:
        flag = azure_tts.compute_rate_flag(Decimal(str(min(r, R_MAX))))
        res = await azure_tts.synthesize(text, voice, str(out), rate=flag)
        tts_calls = 1
        branch = "speedup" if r <= R_MAX else "capped"
        rate, t_final = float(res.applied_rate), max(res.duration_sec, t_orig)
    return _row({**base, "variant": "V3", "tgt_text": text, "tgt_chars": len(text),
                 "t_tts_default": round(t_tts, 3), "r_default": round(r, 3)},
                branch=branch, applied_rate=rate, n_resummarize=0, was_summarized=False,
                t_final=round(t_final, 3), llm_calls=0, tts_calls=tts_calls)


async def run_v4(base: dict, seg: Segment, text: str, t_tts: float, voice: str, tgt: str, out: Path) -> SegmentRow:
    """Gọi ĐÚNG hàm `_synthesize_with_adaptive_rate` của pipeline."""
    before = COUNTER.reset()
    res, final_text, was_sum = await dubbing_service._synthesize_with_adaptive_rate(seg, text, voice, out, tgt)
    used = COUNTER.reset()
    # trả lại số đếm cũ để tổng của video vẫn đúng
    COUNTER.llm, COUNTER.tts, COUNTER.resummarize = (
        before.llm + used.llm, before.tts + used.tts, before.resummarize + used.resummarize)

    t_orig = base["t_orig"]
    t_final = await audio_utils.measure_duration_sec(out)   # sau khi đệm lặng / tăng tốc
    r = t_tts / t_orig if t_orig > 0 else 0.0
    rate = float(res.applied_rate)
    if used.resummarize and r > R_MAX and rate >= R_MAX - 1e-6 and t_final > t_orig * 1.001:
        branch = "capped"
    elif used.resummarize:
        branch = "summarize"
    elif rate > 1.0:
        branch = "speedup"
    else:
        branch = "pad"
    return _row({**base, "variant": "V4", "tgt_text": final_text, "tgt_chars": len(final_text),
                 "t_tts_default": round(t_tts, 3), "r_default": round(r, 3)},
                branch=branch, applied_rate=rate, n_resummarize=used.resummarize,
                was_summarized=was_sum, t_final=round(t_final, 3),
                llm_calls=used.llm, tts_calls=used.tts)


# ---------------------------------------------------------------------------
# Chạy 1 video
# ---------------------------------------------------------------------------
async def run_video(spec: VideoSpec, variants: list[str], run_id: str, out_dir: Path,
                    cache_root: Path, max_chunks: int | None, keep_audio: bool) -> tuple[list[SegmentRow], VideoRow]:
    work = cache_root / spec.id
    work.mkdir(parents=True, exist_ok=True)
    seg_dir = out_dir / "audio" / spec.id
    seg_dir.mkdir(parents=True, exist_ok=True)
    COUNTER.reset()
    rows: list[SegmentRow] = []

    t0 = time.perf_counter()
    audio = await prepare_audio(spec, work)
    t_prepare = time.perf_counter() - t0

    t0 = time.perf_counter()
    duration, chunks, segs_by_chunk, src_lang, cached = await transcribe_cached(spec, audio, work, max_chunks)
    t_asr = time.perf_counter() - t0
    n_seg = sum(len(v) for v in segs_by_chunk.values())
    speech = sum(s.duration for v in segs_by_chunk.values() for s in v)
    covered = sum(c.end_sec - c.start_sec for c in chunks) or 1
    print(f"[{spec.id}] {duration:.0f}s, {len(chunks)} chunk, {n_seg} câu, ngôn ngữ={src_lang}, asr_cache={cached}")

    t_tr = t_tts0 = t_v3 = t_v4 = 0.0
    llm_translate = 0
    for ch in chunks:
        segs = [s for s in segs_by_chunk.get(ch.index, []) if s.duration > 0 and s.text.strip()]
        if not segs:
            continue
        llm_before = COUNTER.llm
        t0 = time.perf_counter()
        one, two = await translate_two_phase(segs, src_lang, spec.target_language)
        t_tr += time.perf_counter() - t0
        llm_translate += COUNTER.llm - llm_before

        for seg, txt1, txt2 in zip(segs, one, two):
            base = dict(run_id=run_id, video_id=spec.id, category=spec.category, chunk_index=ch.index,
                        seq=seg.seq, t_orig=round(seg.duration, 3), src_text=seg.text)
            p = seg_dir / f"c{ch.index}_s{seg.seq}"

            t0 = time.perf_counter()
            tts2 = None
            if "V1" in variants and txt1:
                r1 = await azure_tts.synthesize(txt1, spec.voice_name, f"{p}_v1.mp3")
                rows.append(_default_row(base, "V1", txt1, r1.duration_sec))
            if {"V2", "V3", "V4"} & set(variants) and txt2:
                tts2 = await azure_tts.synthesize(txt2, spec.voice_name, f"{p}_v2.mp3")
                if "V2" in variants:
                    rows.append(_default_row(base, "V2", txt2, tts2.duration_sec))
            t_tts0 += time.perf_counter() - t0
            if tts2 is None:
                continue

            if "V3" in variants:
                t0 = time.perf_counter()
                rows.append(await run_v3(base, txt2, tts2.duration_sec, spec.voice_name, Path(f"{p}_v3.mp3")))
                t_v3 += time.perf_counter() - t0
            if "V4" in variants:
                t0 = time.perf_counter()
                rows.append(await run_v4(base, seg, txt2, tts2.duration_sec, spec.voice_name,
                                         spec.target_language, Path(f"{p}_v4.mp3")))
                t_v4 += time.perf_counter() - t0
        print(f"  chunk {ch.index}: {len(segs)} câu xong")

    if not keep_audio:
        shutil.rmtree(seg_dir, ignore_errors=True)

    vrow = VideoRow(
        run_id=run_id, video_id=spec.id, category=spec.category, duration_sec=round(duration, 1),
        n_chunks=len(chunks), n_segments=n_seg, speech_ratio=round(speech / covered, 3),
        t_prepare_sec=round(t_prepare, 2), t_asr_sec=round(t_asr, 2), asr_cached=cached,
        t_translate_sec=round(t_tr, 2), t_tts_default_sec=round(t_tts0, 2),
        t_v3_sec=round(t_v3, 2), t_v4_sec=round(t_v4, 2),
        llm_calls_translate=llm_translate, tts_calls_total=COUNTER.tts,
        resummarize_calls_v4=COUNTER.resummarize,
    )
    return rows, vrow


def _write_csv(path: Path, rows: list, append: bool) -> None:
    if not rows:
        return
    dicts = [asdict(r) for r in rows]
    for d in dicts:
        d.pop("timings", None)
    new = not path.exists() or not append
    with path.open("a" if append else "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(dicts[0].keys()))
        if new:
            w.writeheader()
        w.writerows(dicts)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, help="File JSON danh sách video (xem videos.example.json)")
    ap.add_argument("--variants", default="V1,V2,V3,V4")
    ap.add_argument("--only", default="", help="Chỉ chạy các video id này (phân cách dấu phẩy)")
    ap.add_argument("--max-chunks", type=int, default=None, help="Giới hạn số chunk/video (chạy thử cho rẻ)")
    ap.add_argument("--out", default=str(Path(__file__).parent / "results"))
    ap.add_argument("--cache", default=str(Path(__file__).parent / ".cache"))
    ap.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--keep-audio", action="store_true", help="Giữ file mp3 từng câu để nghe/đánh giá MOS")
    args = ap.parse_args()

    variants = [v.strip().upper() for v in args.variants.split(",") if v.strip()]
    bad = set(variants) - set(ALL_VARIANTS)
    if bad:
        sys.exit(f"Phương án không hợp lệ: {bad}")

    specs = [VideoSpec(**v) for v in json.loads(Path(args.manifest).read_text(encoding="utf-8"))]
    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        specs = [s for s in specs if s.id in keep]

    out_dir = Path(args.out) / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run_meta.json").write_text(json.dumps({
        "run_id": args.run_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "variants": variants,
        "max_chunks": args.max_chunks,
        "videos": [asdict(s) for s in specs],
        "params": {
            "chunk_minutes": settings.chunk_minutes,
            "r_min": R_MIN, "r_max": R_MAX,
            "max_tts_rate": dubbing_service.MAX_TTS_RATE,
            "max_resummarize_attempts": settings.max_resummarize_attempts,
            "min_speech_ratio": dubbing_service.MIN_SPEECH_RATIO,
            "asr_model": settings.groq_asr_model,
            "llm_model": settings.gemini_model,
            "llm_fallback_models": settings.gemini_models,
        },
        "machine": {"python": sys.version.split()[0], "platform": sys.platform},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    install_counters()
    for spec in specs:
        try:
            rows, vrow = await run_video(spec, variants, args.run_id, out_dir, Path(args.cache),
                                         args.max_chunks, args.keep_audio)
        except Exception as exc:  # 1 video lỗi không làm hỏng cả lượt chạy
            print(f"[{spec.id}] LỖI: {exc!r}")
            continue
        # ghi ngay sau mỗi video để không mất dữ liệu nếu bị ngắt giữa chừng
        _write_csv(out_dir / "segments.csv", rows, append=True)
        _write_csv(out_dir / "videos.csv", [vrow], append=True)
        print(f"[{spec.id}] xong: {len(rows)} dòng, LLM dịch={vrow.llm_calls_translate}, TTS={vrow.tts_calls_total}")

    print(f"\nKết quả: {out_dir}\nPhân tích: python NCKH/experiments/analyze.py {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
