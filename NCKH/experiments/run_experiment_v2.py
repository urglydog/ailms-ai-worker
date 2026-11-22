"""Thực nghiệm SSRC — bản cho pipeline SAU tối ưu (15–22/11/2026).

`run_experiment.py` (bản cũ) giữ nguyên để tái lập số liệu commit `e5a8cb7`; nó KHÔNG chạy được
trên code hiện tại (gọi `_build_adapt_prompt` đã bị gỡ, tăng tốc bằng SSML). Script này dùng đúng
các hàm của pipeline hiện tại; không sửa code app, không ghi DB, không gọi backend.

Bốn phương án (khớp định nghĩa trong NCKH/paper/main.tex, mục Thiết lập thực nghiệm):
  V1  dịch KHÔNG ràng buộc độ dài (`translation._build_direct_prompt`), TTS tốc độ mặc định
  V2  `translation.translate_batch(max_chars=None)` (chỉ ngân sách thời lượng), tốc độ mặc định
  V3  `translate_batch` có `max_chars = cps × T_orig × 1,15` (như pipeline) + tăng tốc `atempo` ≤ ×1,3, KHÔNG rút gọn
  V4  pipeline đầy đủ: cùng bản dịch với V3, gọi thẳng `dubbing_service._synthesize_segments` cho cả chunk
      (TTS song song, rút gọn theo lô tối đa M vòng, `atempo`)

V3 và V4 dùng CHUNG một bản dịch (khác nhau chỉ ở bước rút gọn). Nếu giọng chưa có tốc độ đọc (`tts_cps`)
thì `max_chars = None` và V3/V4 dùng lại bản dịch của V2 (cùng lời gọi) — ghi vào cột `cps_used`.

ASR: Groq Whisper qua `groq_asr.transcribe` (mốc đầu câu theo TỪ ĐẦU TIÊN) + `clamp_stt_segments`, lưu
`.cache/<video>/asr_cache.json` với `asr_version = 2`. Cache cũ (mốc đầu đoạn, không có asr_version) bị bỏ
qua và ghi đè — `check_full_length.py` đọc đúng file này để lấy mốc gốc.

Câu chỉ có dấu câu (`_has_speakable_text` = False) bị loại khỏi MỌI phương án (pipeline thay bằng 0,1 s lặng);
số câu bị loại ghi ở `videos.csv`.

Chạy trong container ai-worker (đứng ở /app):
    python NCKH/experiments/run_experiment_v2.py --manifest NCKH/experiments/videos.json --run-id v3_r1 --keep-audio
    python NCKH/experiments/run_experiment_v2.py --manifest ... --run-id smoke --only lec01 --max-chunks 1   # chạy thử
    python NCKH/experiments/run_experiment_v2.py --manifest ... --run-id v3_r2 --variants V4               # V4 lần 2
Rồi: python NCKH/experiments/analyze.py NCKH/experiments/results/<run_id>

Đầu ra (results/<run_id>/): segments.csv (cùng cột với bản cũ — analyze.py, sample_fidelity.py,
check_full_length.py đọc được), videos.csv (thêm số lời gọi LLM/TTS theo phương án), run_meta.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

AI_WORKER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_WORKER_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import audio_utils, media  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import Segment  # noqa: E402
from app.providers import azure_tts, gemini, groq_asr  # noqa: E402
from app.providers.base import ProviderInvalidResponse  # noqa: E402
from app.services import dubbing_service, translation  # noqa: E402

from run_experiment import VideoSpec, _default_row, _row, _write_csv, prepare_audio  # noqa: E402

R_MIN = float(dubbing_service.R_LOWER_BOUND)
R_MAX = float(dubbing_service.R_UPPER_BOUND)
MAX_TEMPO = float(dubbing_service._MAX_TEMPO)
ALL_VARIANTS = ["V1", "V2", "V3", "V4"]
ASR_VERSION = 2


# ---------------------------------------------------------------------------- đếm lời gọi
class Counter:
    def __init__(self) -> None:
        self.llm = 0
        self.tts = 0
        self.resum_batch = 0

    def snap(self) -> tuple[int, int, int]:
        return self.llm, self.tts, self.resum_batch


C = Counter()
_orig_generate = gemini.generate
_orig_synth = azure_tts.synthesize
_orig_resum_batch = translation.resummarize_batch


async def _gen(*a, **k):
    C.llm += 1
    return await _orig_generate(*a, **k)


async def _synth(*a, **k):
    C.tts += 1
    return await _orig_synth(*a, **k)


async def _resum(*a, **k):
    C.resum_batch += 1
    return await _orig_resum_batch(*a, **k)


def install_counters() -> None:
    # translation/dubbing_service gọi qua thuộc tính module -> vá ở module là đủ
    gemini.generate = _gen
    azure_tts.synthesize = _synth
    translation.resummarize_batch = _resum


# ---------------------------------------------------------------------------- dữ liệu video
@dataclass
class VideoRowV2:
    run_id: str
    video_id: str
    category: str
    duration_sec: float
    n_chunks: int
    n_segments: int
    n_unspeakable: int
    n_chunks_skipped_low_speech: int
    speech_ratio: float
    asr_cached: bool
    cps_before: str
    cps_after: str
    t_asr_sec: float
    t_translate_sec: float
    t_tts_default_sec: float
    t_v3_sec: float
    t_v4_sec: float
    llm_V1: int
    llm_V2: int
    llm_V34_translate: int
    llm_V4_resummarize: int
    resummarize_batch_calls_V4: int
    tts_V1: int
    tts_V2: int
    tts_V3: int
    tts_V4: int
    # để analyze.py bản cũ vẫn chạy (tổng lời gọi dịch)
    llm_calls_translate: int = 0
    tts_calls_total: int = 0
    resummarize_calls_v4: int = 0


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=AI_WORKER_ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip() or "?"
    except Exception:
        return "?"


async def _cps(voice: str) -> float | None:
    return await dubbing_service._voice_chars_per_sec(voice)


# ---------------------------------------------------------------------------- ASR (mốc mới)
async def transcribe_v2(spec: VideoSpec, audio: Path, work: Path, max_chunks: int | None):
    duration = await media.probe_duration_sec(audio)
    chunks = dubbing_service.split_into_chunks(int(duration), settings.chunk_minutes)
    if max_chunks:
        chunks = chunks[:max_chunks]

    cache = work / "asr_cache.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if (data.get("asr_version") == ASR_VERSION and data.get("chunk_minutes") == settings.chunk_minutes
                and len(data["chunks"]) >= len(chunks)):
            segs = {int(k): [Segment(**s) for s in v] for k, v in data["chunks"].items() if int(k) < len(chunks)}
            return duration, chunks, segs, data["language"], data.get("skipped", []), True

    segs: dict[int, list[Segment]] = {}
    skipped: list[int] = []
    language = ""
    seq = 1
    for ch in chunks:
        wav = work / f"chunk_{ch.index}.wav"
        await audio_utils.extract_range(audio, ch.start_sec, ch.end_sec, wav)
        stt = await groq_asr.transcribe(str(wav))
        chunk_len = ch.end_sec - ch.start_sec
        language = language or stt.language
        segs[ch.index] = []
        if chunk_len <= 0 or stt.speech_duration_sec / chunk_len < dubbing_service.MIN_SPEECH_RATIO:
            skipped.append(ch.index)      # pipeline: giữ audio gốc cho đoạn này
            continue
        audio_len = min(float(chunk_len), stt.duration_sec) if stt.duration_sec > 0 else float(chunk_len)
        for start, end, text in dubbing_service.clamp_stt_segments(stt.segments, audio_len):
            segs[ch.index].append(Segment(seq=seq, start=ch.start_sec + start, end=ch.start_sec + end, text=text))
            seq += 1
    cache.write_text(json.dumps({
        "asr_version": ASR_VERSION, "chunk_minutes": settings.chunk_minutes, "language": language,
        "skipped": skipped, "chunks": {str(k): [asdict(s) for s in v] for k, v in segs.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return duration, chunks, segs, language, skipped, False


# ---------------------------------------------------------------------------- dịch
async def translate_v1(segs: list[Segment], src: str, tgt: str) -> list[str]:
    numbered = {str(i + 1): s.text for i, s in enumerate(segs)}
    # 22/11/2026: Gemini 3.6 Flash (thinking minimal) thỉnh thoảng trả JSON hỏng cho lời gọi V1
    # (bắt gặp 2/3 lần chạy lec01, cùng vị trí câu "Von Neumann"). Pipeline thật có thử lại cả chunk
    # còn V1 là phương án nền chỉ có trong script đo, nên thử lại tối đa 3 lần; mỗi lần thử đều tính
    # vào số lời gọi LLM của V1 (gemini.generate bị vá để đếm) và được in ra để ghi vào REPORT.
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        res = await gemini.generate(translation._build_direct_prompt(numbered, src, tgt), thinking_level=translation._thinking())
        try:
            m = translation._extract_json(res.text)
            break
        except ProviderInvalidResponse as exc:
            last_exc = exc
            print(f"  [V1] JSON hỏng lần {attempt}/3 — thử lại: {str(exc)[:120]}", flush=True)
    else:
        raise last_exc  # type: ignore[misc]
    return [(translation._as_text(m.get(str(i + 1))) or s.text).strip() for i, s in enumerate(segs)]


# ---------------------------------------------------------------------------- TTS mặc định song song
async def tts_all(texts: list[str], voice: str, paths: list[Path]) -> list[float]:
    sem = asyncio.Semaphore(max(1, settings.tts_concurrency))

    async def one(t: str, p: Path) -> float:
        async with sem:
            return (await azure_tts.synthesize(t, voice, str(p))).duration_sec

    return list(await asyncio.gather(*(one(t, p) for t, p in zip(texts, paths))))


def _branch_v3(r: float) -> str:
    if r <= R_MIN:
        return "pad"
    return "speedup" if r <= R_MAX else "capped"


# ---------------------------------------------------------------------------- 1 video
async def run_video(spec: VideoSpec, variants: list[str], run_id: str, out_dir: Path, cache_root: Path,
                    max_chunks: int | None, keep_audio: bool):
    work = cache_root / spec.id
    work.mkdir(parents=True, exist_ok=True)
    adir = out_dir / "audio" / spec.id
    adir.mkdir(parents=True, exist_ok=True)
    rows = []
    calls = {k: 0 for k in ["llm_V1", "llm_V2", "llm_V34", "llm_V4", "rb_V4", "tts_V1", "tts_V2", "tts_V3", "tts_V4"]}
    t = {k: 0.0 for k in ["asr", "tr", "tts0", "v3", "v4"]}
    cps_before = await _cps(spec.voice_name)

    audio = await prepare_audio(spec, work)
    t0 = time.perf_counter()
    duration, chunks, segs_by_chunk, src_lang, skipped, cached = await transcribe_v2(spec, audio, work, max_chunks)
    t["asr"] = time.perf_counter() - t0

    n_seg = n_unspeak = 0
    speech = 0.0
    for ch in chunks:
        all_segs = segs_by_chunk.get(ch.index, [])
        segs = [s for s in all_segs if dubbing_service._has_speakable_text(s.text) and s.duration > 0]
        n_unspeak += len(all_segs) - len(segs)
        n_seg += len(segs)
        speech += sum(s.duration for s in segs)
        if not segs:
            continue

        # ---- dịch
        t0 = time.perf_counter()
        tx: dict[str, list[str]] = {}
        if "V1" in variants:
            l0 = C.llm
            tx["V1"] = await translate_v1(segs, src_lang, spec.target_language)
            calls["llm_V1"] += C.llm - l0
        need_v2 = "V2" in variants
        cps = await _cps(spec.voice_name) if {"V3", "V4"} & set(variants) else None
        v2_cost = 0
        if need_v2 or ({"V3", "V4"} & set(variants) and not cps):
            l0 = C.llm
            tx["V2"] = await translation.translate_batch(segs, src_lang, spec.target_language, max_chars=None)
            v2_cost = C.llm - l0
            if need_v2:
                calls["llm_V2"] += v2_cost
        if {"V3", "V4"} & set(variants):
            if cps:
                max_chars = [max(4, int(cps * s.duration * dubbing_service._TARGET_R)) for s in segs]
                l0 = C.llm
                tx["V34"] = await translation.translate_batch(segs, src_lang, spec.target_language, max_chars=max_chars)
                calls["llm_V34"] += C.llm - l0
            else:
                tx["V34"] = tx["V2"]           # chưa có tốc độ đọc: cùng bản dịch với V2
                calls["llm_V34"] += v2_cost    # tính chi phí dịch cho V3/V4 như một lời gọi riêng
        t["tr"] += time.perf_counter() - t0
        cps_used = f"{cps:.3f}" if cps else "none"

        def base(i: int, seg: Segment) -> dict:
            return dict(run_id=run_id, video_id=spec.id, category=spec.category, chunk_index=ch.index,
                        seq=seg.seq, t_orig=round(seg.duration, 3), src_text=seg.text)

        def paths(tag: str) -> list[Path]:
            return [adir / f"c{ch.index}_s{s.seq}_{tag}.mp3" for s in segs]

        # ---- V1, V2, V3 (TTS mặc định)
        t0 = time.perf_counter()
        dur: dict[str, list[float]] = {}
        for v, key in (("V1", "V1"), ("V2", "V2"), ("V3", "V34")):
            if v not in variants:
                continue
            tag = "v3raw" if v == "V3" else v.lower()
            s0 = C.tts
            dur[v] = await tts_all(tx[key], spec.voice_name, paths(tag))
            calls[f"tts_{v}"] += C.tts - s0
            if v in ("V1", "V2"):
                for i, seg in enumerate(segs):
                    rows.append(_default_row(base(i, seg), v, tx[key][i], dur[v][i]))
        t["tts0"] += time.perf_counter() - t0

        if "V3" in variants:
            t0 = time.perf_counter()
            raw, out = paths("v3raw"), paths("v3")
            for i, seg in enumerate(segs):
                r = dur["V3"][i] / seg.duration
                shutil.copyfile(raw[i], out[i])
                factor = min(r, MAX_TEMPO) if r > R_MIN else 1.0
                if factor > 1.0:
                    await audio_utils.change_tempo(out[i], factor)
                t_final = max(dur["V3"][i] / factor, seg.duration)
                rows.append(_row({**base(i, seg), "variant": "V3", "tgt_text": tx["V34"][i],
                                  "tgt_chars": len(tx["V34"][i]), "t_tts_default": round(dur["V3"][i], 3),
                                  "r_default": round(r, 3)},
                                 branch=_branch_v3(r), applied_rate=round(factor, 3), n_resummarize=0,
                                 was_summarized=False, t_final=round(t_final, 3), llm_calls=0,
                                 tts_calls=1))
                if not keep_audio:
                    raw[i].unlink(missing_ok=True)
            t["v3"] += time.perf_counter() - t0

        if "V4" in variants:
            t0 = time.perf_counter()
            out = paths("v4")
            l0, s0, b0 = C.snap()
            res = await dubbing_service._synthesize_segments(segs, list(tx["V34"]), spec.voice_name, out,
                                                             spec.target_language)
            calls["llm_V4"] += C.llm - l0
            calls["tts_V4"] += C.tts - s0
            calls["rb_V4"] += C.resum_batch - b0
            for i, seg in enumerate(segs):
                synth, text, summarized = res[i]
                rate = float(synth.applied_rate)
                t_file = await audio_utils.measure_duration_sec(out[i])
                t_final = max(t_file, seg.duration)
                r0 = dur["V3"][i] / seg.duration if "V3" in dur else (t_file * rate) / seg.duration
                if rate >= MAX_TEMPO - 1e-6 and t_final > seg.duration * 1.01:
                    branch = "capped"
                elif summarized:
                    branch = "summarize"
                elif rate > 1.0:
                    branch = "speedup"
                else:
                    branch = "pad"
                rows.append(_row({**base(i, seg), "variant": "V4", "tgt_text": text, "tgt_chars": len(text),
                                  "t_tts_default": round(dur["V3"][i], 3) if "V3" in dur else 0.0,
                                  "r_default": round(r0, 3)},
                                 branch=branch, applied_rate=round(rate, 3), n_resummarize=int(summarized),
                                 was_summarized=bool(summarized), t_final=round(t_final, 3),
                                 llm_calls=0, tts_calls=0))
            t["v4"] += time.perf_counter() - t0
        print(f"  [{spec.id}] chunk {ch.index}: {len(segs)} câu, cps={cps_used}")

    if not keep_audio:
        shutil.rmtree(adir, ignore_errors=True)
    covered = sum(c.end_sec - c.start_sec for c in chunks) or 1
    cps_after = await _cps(spec.voice_name)
    vrow = VideoRowV2(
        run_id=run_id, video_id=spec.id, category=spec.category, duration_sec=round(duration, 1),
        n_chunks=len(chunks), n_segments=n_seg, n_unspeakable=n_unspeak, n_chunks_skipped_low_speech=len(skipped),
        speech_ratio=round(speech / covered, 3), asr_cached=cached,
        cps_before=f"{cps_before:.3f}" if cps_before else "none", cps_after=f"{cps_after:.3f}" if cps_after else "none",
        t_asr_sec=round(t["asr"], 2), t_translate_sec=round(t["tr"], 2), t_tts_default_sec=round(t["tts0"], 2),
        t_v3_sec=round(t["v3"], 2), t_v4_sec=round(t["v4"], 2),
        llm_V1=calls["llm_V1"], llm_V2=calls["llm_V2"], llm_V34_translate=calls["llm_V34"],
        llm_V4_resummarize=calls["llm_V4"], resummarize_batch_calls_V4=calls["rb_V4"],
        tts_V1=calls["tts_V1"], tts_V2=calls["tts_V2"], tts_V3=calls["tts_V3"], tts_V4=calls["tts_V4"],
        llm_calls_translate=calls["llm_V1"] + calls["llm_V2"] + calls["llm_V34"],
        tts_calls_total=sum(calls[k] for k in ("tts_V1", "tts_V2", "tts_V3", "tts_V4")),
        resummarize_calls_v4=calls["llm_V4"],
    )
    return rows, vrow


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--variants", default="V1,V2,V3,V4")
    ap.add_argument("--only", default="")
    ap.add_argument("--max-chunks", type=int, default=None)
    ap.add_argument("--out", default=str(Path(__file__).parent / "results"))
    ap.add_argument("--cache", default=str(Path(__file__).parent / ".cache"))
    ap.add_argument("--run-id", default=datetime.now().strftime("v2_%Y%m%d_%H%M%S"))
    ap.add_argument("--keep-audio", action="store_true")
    args = ap.parse_args()

    variants = [v.strip().upper() for v in args.variants.split(",") if v.strip()]
    if set(variants) - set(ALL_VARIANTS):
        sys.exit(f"Phương án không hợp lệ: {set(variants) - set(ALL_VARIANTS)}")
    specs = [VideoSpec(**v) for v in json.loads(Path(args.manifest).read_text(encoding="utf-8"))]
    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        specs = [s for s in specs if s.id in keep]

    out_dir = Path(args.out) / args.run_id
    if (out_dir / "segments.csv").exists():
        sys.exit(f"{out_dir} đã có kết quả — dùng --run-id khác (tránh dùng lại cache TTS của lần trước)")
    out_dir.mkdir(parents=True, exist_ok=True)
    voices = sorted({s.voice_name for s in specs})
    meta = {
        "run_id": args.run_id, "script": "run_experiment_v2.py", "commit": _git_commit(),
        "started_at": datetime.now().isoformat(timespec="seconds"), "variants": variants,
        "max_chunks": args.max_chunks, "videos": [asdict(s) for s in specs],
        "params": {
            "chunk_minutes": settings.chunk_minutes, "r_min": R_MIN, "r_max": R_MAX, "max_tempo": MAX_TEMPO,
            "max_resummarize_attempts": settings.max_resummarize_attempts,
            "min_resummarize_frame_sec": settings.min_resummarize_frame_sec,
            "target_r_max_chars": dubbing_service._TARGET_R, "min_speech_ratio": dubbing_service.MIN_SPEECH_RATIO,
            "asr_model": settings.groq_asr_model, "llm_model": settings.gemini_model,
            "llm_fallback_models": settings.gemini_models, "dubbing_thinking_level": settings.dubbing_thinking_level,
            "tts_concurrency": settings.tts_concurrency, "timeline_engine": settings.timeline_engine,
            "bgm_separation": settings.bgm_separation,
        },
        "tts_cps_before": {v: await _cps(v) for v in voices},
        "machine": {"python": sys.version.split()[0], "platform": sys.platform},
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    install_counters()
    for spec in specs:
        try:
            rows, vrow = await run_video(spec, variants, args.run_id, out_dir, Path(args.cache),
                                         args.max_chunks, args.keep_audio)
        except Exception as exc:
            print(f"[{spec.id}] LỖI: {exc!r}")
            meta.setdefault("errors", {})[spec.id] = repr(exc)
            continue
        _write_csv(out_dir / "segments.csv", rows, append=True)
        _write_csv(out_dir / "videos.csv", [vrow], append=True)
        print(f"[{spec.id}] xong: {len(rows)} dòng | LLM V1/V2/V34/V4-rutgon = {vrow.llm_V1}/{vrow.llm_V2}/"
              f"{vrow.llm_V34_translate}/{vrow.llm_V4_resummarize} | TTS V4 = {vrow.tts_V4}")
    meta["tts_cps_after"] = {v: await _cps(v) for v in voices}
    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    (out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nKết quả: {out_dir}\nPhân tích: python NCKH/experiments/analyze.py {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
