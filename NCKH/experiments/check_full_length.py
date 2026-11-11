"""Kiểm chứng trên AUDIO THẬT: ghép lại âm thanh lồng tiếng của cả bài (đúng cách pipeline ghép) rồi đo
(1) tổng thời lượng so với thời lượng gốc, (2) thời lượng từng đoạn so với khung đoạn,
(3) độ trễ mốc bắt đầu từng câu so với mốc gốc (đo từ độ dài file mp3 thật, không phải từ CSV).

Cách ghép lặp lại dubbing_service._process_chunk: khoảng lặng trước câu = max(0, start - prev_end) của bản gốc,
đệm cuối đoạn nếu thiếu (> 0.05 s), rồi nối các đoạn bằng audio_utils.concat_files. Dữ liệu câu lấy từ
.cache/<video>/asr_cache.json (mốc gốc) và results/<run>/audio/<video>/c<chunk>_s<seq>_v<k>.mp3 (cần --keep-audio).

Chạy TRONG container ai-worker bằng user thường (để file tạo ra không thuộc root):
    docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/check_full_length.py \
        NCKH/experiments/results/full_r1 --variants V2,V4
Xuất: <run_dir>/check_full_length.json, check_full_length.md, drift_measured.csv (từng câu)
Không ghi vào DB, không gọi API.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics as st
import sys
import tempfile
from pathlib import Path

AI_WORKER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_WORKER_ROOT))

from app import audio_utils  # noqa: E402
from app.models import Segment  # noqa: E402
from app.services import dubbing_service  # noqa: E402

CACHE_ROOT = Path(__file__).parent / ".cache"


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))] if s else 0.0


async def check_video(run_dir: Path, vid: str, duration: float, variant: str, tmp: Path, rows_out: list[dict]) -> dict:
    cache = json.loads((CACHE_ROOT / vid / "asr_cache.json").read_text(encoding="utf-8"))
    chunk_minutes = int(cache["chunk_minutes"])
    chunks = dubbing_service.split_into_chunks(int(duration), chunk_minutes)
    audio_dir = run_dir / "audio" / vid
    chunk_files: list[Path] = []
    per_chunk: list[dict] = []
    onset_drifts: list[float] = []
    carry = 0.0   # tổng độ dài thừa/thiếu đã tích lũy của các đoạn trước (đo thật)
    missing: list[str] = []

    for ch in chunks:
        segs = [Segment(**s) for s in cache["chunks"].get(str(ch.index), [])]
        paths: list[Path] = []
        gaps: list[float] = []
        prev_end = float(ch.start_sec)
        for seg in segs:
            f = audio_dir / f"c{ch.index}_s{seg.seq}_{variant.lower()}.mp3"
            if not f.exists():
                missing.append(f.name)
                continue
            paths.append(f)
            gaps.append(max(0.0, seg.start - prev_end))
            prev_end = seg.end
        if missing:
            break
        out = tmp / f"{vid}_{variant}_chunk{ch.index}.mp3"
        if paths:
            await audio_utils.concat_with_leading_silence(paths, gaps, out)
            trailing = max(0.0, ch.end_sec - prev_end)
            if trailing > 0.05:
                await audio_utils.pad_silence(out, trailing)
        else:
            raise RuntimeError(f"{vid} chunk {ch.index}: không có câu nào")
        actual = await audio_utils.measure_duration_sec(out)
        expected = float(ch.end_sec - ch.start_sec)

        # Mốc bắt đầu thật của từng câu trong đoạn = tổng (khoảng lặng + độ dài file) các câu trước
        pos = 0.0
        for seg, f, gap in zip(segs, paths, gaps):
            pos += gap
            dur = await audio_utils.measure_duration_sec(f)
            onset_dub = ch.start_sec + carry + pos          # mốc bắt đầu thật trong file ghép cả bài
            drift = onset_dub - seg.start                   # trễ (+) / sớm (−) so với mốc gốc
            onset_drifts.append(drift)
            rows_out.append({
                "video_id": vid, "variant": variant, "chunk_index": ch.index, "seq": seg.seq,
                "t_orig": round(seg.end - seg.start, 3), "t_file": round(dur, 3),
                "onset_orig_s": round(seg.start, 3), "onset_dub_s": round(onset_dub, 3),
                "onset_drift_s": round(drift, 3),
            })
            pos += dur
        per_chunk.append({
            "chunk": ch.index, "expected_s": round(expected, 2), "actual_s": round(actual, 2),
            "diff_s": round(actual - expected, 2),
        })
        carry += actual - expected
        chunk_files.append(out)

    if missing:
        return {"error": f"thiếu {len(missing)} file câu (ví dụ {missing[:3]}); không ghép được", "variant": variant}

    final = tmp / f"{vid}_{variant}_final.mp3"
    await audio_utils.concat_files(chunk_files, final)
    final_dur = await audio_utils.measure_duration_sec(final)
    return {
        "variant": variant,
        "original_duration_s": round(duration, 2),
        "final_duration_s": round(final_dur, 2),
        "diff_s": round(final_dur - duration, 2),
        "diff_pct": round(100.0 * (final_dur - duration) / duration, 2),
        "per_chunk": per_chunk,
        "onset_drift_mean_s": round(st.mean(onset_drifts), 2) if onset_drifts else 0.0,
        "onset_drift_p95_s": round(p95(onset_drifts), 2),
        "onset_drift_max_s": round(max(onset_drifts), 2) if onset_drifts else 0.0,
        "pct_sentences_drift_gt_1s": round(100.0 * sum(1 for x in onset_drifts if x > 1.0) / max(1, len(onset_drifts)), 1),
        "pct_sentences_drift_gt_2s": round(100.0 * sum(1 for x in onset_drifts if x > 2.0) / max(1, len(onset_drifts)), 1),
    }


async def amain() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--variants", default="V2,V4")
    ap.add_argument("--only", default="", help="Chỉ kiểm các video id này (phân cách dấu phẩy)")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = (AI_WORKER_ROOT / run_dir).resolve()
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    with (run_dir / "videos.csv").open(encoding="utf-8-sig", newline="") as fh:
        videos = [r for r in csv.DictReader(fh) if not only or r["video_id"] in only]

    rows_out: list[dict] = []
    result: dict = {"run_id": run_dir.name, "videos": {}}
    with tempfile.TemporaryDirectory(prefix="check_full_length_") as td:
        tmp = Path(td)
        for v in videos:
            vid = v["video_id"]
            result["videos"][vid] = {}
            for variant in variants:
                print(f"[{vid}] {variant} ...", flush=True)
                result["videos"][vid][variant] = await check_video(
                    run_dir, vid, float(v["duration_sec"]), variant, tmp, rows_out)

    (run_dir / "check_full_length.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows_out:
        with (run_dir / "drift_measured.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

    lines = [f"# Kiểm tra ghép toàn bài trên audio thật — run `{run_dir.name}`", "",
             "| Video | Phương án | Gốc (s) | Sau ghép (s) | Chênh (s) | Chênh (%) | Trễ mốc câu TB (s) | p95 | max | % câu trễ >1 s | >2 s |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for vid, per_v in result["videos"].items():
        for variant, r in per_v.items():
            if "error" in r:
                lines.append(f"| {vid} | {variant} | – | – | – | – | – | – | – | – | – |  <!-- {r['error']} -->")
                continue
            lines.append(f"| {vid} | {variant} | {r['original_duration_s']} | {r['final_duration_s']} | {r['diff_s']} | "
                         f"{r['diff_pct']} | {r['onset_drift_mean_s']} | {r['onset_drift_p95_s']} | {r['onset_drift_max_s']} | "
                         f"{r['pct_sentences_drift_gt_1s']} | {r['pct_sentences_drift_gt_2s']} |")
    errs = [(vid, var, r["error"]) for vid, pv in result["videos"].items() for var, r in pv.items() if "error" in r]
    if errs:
        lines += ["", "## Không ghép được", ""] + [f"- {a} {b}: {c}" for a, b, c in errs]
    (run_dir / "check_full_length.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(amain())
