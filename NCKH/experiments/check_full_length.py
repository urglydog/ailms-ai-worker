"""Kiểm chứng trên AUDIO THẬT: ghép lại âm thanh lồng tiếng của cả bài rồi đo
(1) tổng thời lượng so với thời lượng gốc, (2) thời lượng từng đoạn so với khung đoạn,
(3) độ trễ mốc bắt đầu từng câu so với mốc gốc (đo từ độ dài file mp3 thật, không phải từ CSV).

Hai cách ghép (chọn bằng --assembly):
  old : cách TRƯỚC 11/11/2026 — khoảng lặng trước câu = max(0, start - prev_end) của bản gốc, đệm cuối đoạn nếu thiếu
        (`audio_utils.concat_with_leading_silence` + `pad_silence`), nối đoạn bằng `concat_files`.
  new : cách SAU bản sửa 11/11/2026 — xếp câu theo mốc tuyệt đối và khớp đúng độ dài đoạn bằng chính hàm của pipeline
        `audio_utils.place_on_timeline` (tăng tốc cả đoạn tối đa MAX_CHUNK_TEMPO, phần dư bị cắt); mốc ASR được kẹp bằng
        `dubbing_service.clamp_stt_segments` (câu nằm ngoài audio bị bỏ, `end` kẹp theo biên đoạn).
        Lưu ý: file câu của các run chạy TRƯỚC bản sửa được đệm lặng tới khung gốc CHƯA kẹp; với câu bị kẹp mốc ở nhánh
        `pad`, script cắt bớt phần lặng thừa về đúng khung đã kẹp (như pipeline mới sẽ tạo ra).

Dữ liệu: .cache/<video>/asr_cache.json (mốc gốc), results/<run>/audio/<video>/c<chunk>_s<seq>_v<k>.mp3 (cần --keep-audio),
results/<run>/segments.csv (nhánh của từng câu).

Chạy TRONG container ai-worker bằng user thường (để file tạo ra không thuộc root):
    docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/check_full_length.py \
        NCKH/experiments/results/full_r1 --variants V2,V4 --assembly both
Xuất: <run_dir>/check_full_length.json, check_full_length.md, drift_measured.csv (từng câu, có cột assembly)
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
from types import SimpleNamespace

AI_WORKER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_WORKER_ROOT))

from pydub import AudioSegment  # noqa: E402

from app import audio_utils  # noqa: E402
from app.services import dubbing_service  # noqa: E402

CACHE_ROOT = Path(__file__).parent / ".cache"
_DUR_CACHE: dict[str, float] = {}


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))] if s else 0.0


async def file_dur(path: Path) -> float:
    key = str(path)
    if key not in _DUR_CACHE:
        _DUR_CACHE[key] = await audio_utils.measure_duration_sec(path)
    return _DUR_CACHE[key]


def drift_stats(drifts: list[float]) -> dict:
    n = max(1, len(drifts))
    ab = [abs(x) for x in drifts]
    return {
        "n_sentences": len(drifts),
        "drift_signed_mean_s": round(st.mean(drifts), 2) if drifts else 0.0,
        "drift_abs_mean_s": round(st.mean(ab), 2) if ab else 0.0,
        "drift_abs_p95_s": round(p95(ab), 2),
        "drift_max_late_s": round(max(drifts), 2) if drifts else 0.0,
        "drift_max_early_s": round(-min(drifts), 2) if drifts and min(drifts) < 0 else 0.0,
        "pct_abs_drift_gt_1s": round(100.0 * sum(1 for x in ab if x > 1.0) / n, 1),
        "pct_abs_drift_gt_2s": round(100.0 * sum(1 for x in ab if x > 2.0) / n, 1),
        "pct_late_gt_1s": round(100.0 * sum(1 for x in drifts if x > 1.0) / n, 1),
        "pct_late_gt_2s": round(100.0 * sum(1 for x in drifts if x > 2.0) / n, 1),
    }


async def assemble_old(run_dir: Path, vid: str, duration: float, variant: str, cache: dict, tmp: Path,
                       rows_out: list[dict]) -> dict:
    chunks = dubbing_service.split_into_chunks(int(duration), int(cache["chunk_minutes"]))
    audio_dir = run_dir / "audio" / vid
    chunk_files, per_chunk, drifts, missing = [], [], [], []
    carry = 0.0
    for ch in chunks:
        segs = cache["chunks"].get(str(ch.index), [])
        paths, gaps, kept = [], [], []
        prev_end = float(ch.start_sec)
        for s in segs:
            f = audio_dir / f"c{ch.index}_s{s['seq']}_{variant.lower()}.mp3"
            if not f.exists():
                missing.append(f.name)
                continue
            paths.append(f)
            gaps.append(max(0.0, s["start"] - prev_end))
            kept.append(s)
            prev_end = s["end"]
        if missing:
            return {"error": f"thiếu {len(missing)} file câu (ví dụ {missing[:3]}); không ghép được"}
        if not paths:
            return {"error": f"chunk {ch.index}: không có câu nào"}
        out = tmp / f"{vid}_{variant}_old_chunk{ch.index}.mp3"
        await audio_utils.concat_with_leading_silence(paths, gaps, out)
        trailing = max(0.0, ch.end_sec - prev_end)
        if trailing > 0.05:
            await audio_utils.pad_silence(out, trailing)
        actual = await audio_utils.measure_duration_sec(out)
        expected = float(ch.end_sec - ch.start_sec)
        pos = 0.0
        for s, f, gap in zip(kept, paths, gaps):
            pos += gap
            d = await file_dur(f)
            onset_dub = ch.start_sec + carry + pos
            drift = onset_dub - s["start"]
            drifts.append(drift)
            rows_out.append({"assembly": "old", "video_id": vid, "variant": variant, "chunk_index": ch.index,
                             "seq": s["seq"], "t_orig": round(s["end"] - s["start"], 3), "t_file": round(d, 3),
                             "onset_orig_s": round(s["start"], 3), "onset_dub_s": round(onset_dub, 3),
                             "onset_drift_s": round(drift, 3)})
            pos += d
        per_chunk.append({"chunk": ch.index, "expected_s": round(expected, 2), "actual_s": round(actual, 2),
                          "diff_s": round(actual - expected, 2), "tempo_applied": 1.0, "cut_tail_s": 0.0})
        carry += actual - expected
        chunk_files.append(out)
    final = tmp / f"{vid}_{variant}_old_final.mp3"
    await audio_utils.concat_files(chunk_files, final)
    final_dur = await audio_utils.measure_duration_sec(final)
    return {"original_duration_s": round(duration, 2), "final_duration_s": round(final_dur, 2),
            "diff_s": round(final_dur - duration, 2), "diff_pct": round(100.0 * (final_dur - duration) / duration, 2),
            "per_chunk": per_chunk, "n_chunks_sped_up": 0, "max_tempo": 1.0, "total_cut_tail_s": 0.0,
            "n_segments_dropped_by_clamp": 0, **drift_stats(drifts)}


async def assemble_new(run_dir: Path, vid: str, duration: float, variant: str, cache: dict, tmp: Path,
                       rows_out: list[dict], branch_of: dict) -> dict:
    chunks = dubbing_service.split_into_chunks(int(duration), int(cache["chunk_minutes"]))
    audio_dir = run_dir / "audio" / vid
    chunk_files, per_chunk, drifts, missing = [], [], [], []
    dropped = 0
    for ch in chunks:
        chunk_len = float(ch.end_sec - ch.start_sec)
        raw = cache["chunks"].get(str(ch.index), [])
        # Mốc trong cache là tuyệt đối -> đổi về tương đối trong đoạn rồi kẹp bằng hàm của pipeline (1c).
        rel = [SimpleNamespace(start=s["start"] - ch.start_sec, end=s["end"] - ch.start_sec,
                               text=f"{s['seq']}\x00{s['text']}") for s in raw]
        clamped = dubbing_service.clamp_stt_segments(rel, chunk_len)
        dropped += len(raw) - len(clamped)
        by_seq = {s["seq"]: s for s in raw}
        paths, desired, meta = [], [], []
        for start_rel, end_rel, tagged in clamped:
            seq = int(tagged.split("\x00", 1)[0])
            src = by_seq[seq]
            f = audio_dir / f"c{ch.index}_s{seq}_{variant.lower()}.mp3"
            if not f.exists():
                missing.append(f.name)
                continue
            was_clamped = (src["end"] - ch.start_sec) > end_rel + 1e-6
            frame = end_rel - start_rel
            if was_clamped and branch_of.get((vid, variant, ch.index, seq)) == "pad":
                # file cũ được đệm lặng tới khung CHƯA kẹp -> cắt phần lặng thừa về khung đã kẹp
                d = await file_dur(f)
                if d > frame + 0.05:
                    trimmed = tmp / f"{vid}_{variant}_c{ch.index}_s{seq}_trim.mp3"
                    await asyncio.to_thread(
                        lambda src_f=f, out_f=trimmed, ms=int(frame * 1000):
                        AudioSegment.from_file(str(src_f))[:ms].export(str(out_f), format="mp3"))
                    f = trimmed
            paths.append(f)
            desired.append(max(0.0, start_rel))
            meta.append((seq, start_rel, end_rel))
        if missing:
            return {"error": f"thiếu {len(missing)} file câu (ví dụ {missing[:3]}); không ghép được"}
        if not paths:
            return {"error": f"chunk {ch.index}: không có câu nào"}
        out = tmp / f"{vid}_{variant}_new_chunk{ch.index}.mp3"
        tl = await audio_utils.place_on_timeline(paths, desired, chunk_len, out)
        durs = [await file_dur(p) for p in paths]
        onsets = audio_utils.plan_onsets(desired, durs)
        tempo = tl.tempo_applied or 1.0
        cut_tail = max(0.0, tl.raw_length_sec / tempo - chunk_len)
        for (seq, start_rel, end_rel), onset, d in zip(meta, onsets, durs):
            onset_dub = ch.start_sec + onset / tempo
            drift = onset_dub - (ch.start_sec + start_rel)
            drifts.append(drift)
            rows_out.append({"assembly": "new", "video_id": vid, "variant": variant, "chunk_index": ch.index,
                             "seq": seq, "t_orig": round(end_rel - start_rel, 3), "t_file": round(d, 3),
                             "onset_orig_s": round(ch.start_sec + start_rel, 3), "onset_dub_s": round(onset_dub, 3),
                             "onset_drift_s": round(drift, 3)})
        per_chunk.append({"chunk": ch.index, "expected_s": round(chunk_len, 2), "actual_s": round(tl.final_length_sec, 2),
                          "diff_s": round(tl.final_length_sec - chunk_len, 2), "raw_length_s": tl.raw_length_sec,
                          "tempo_applied": tl.tempo_applied, "cut_tail_s": round(cut_tail, 2),
                          "max_delay_before_tempo_s": tl.max_delay_sec})
        chunk_files.append(out)
    final = tmp / f"{vid}_{variant}_new_final.mp3"
    await audio_utils.concat_files(chunk_files, final)
    final_dur = await audio_utils.measure_duration_sec(final)
    return {"original_duration_s": round(duration, 2), "final_duration_s": round(final_dur, 2),
            "diff_s": round(final_dur - duration, 2), "diff_pct": round(100.0 * (final_dur - duration) / duration, 2),
            "per_chunk": per_chunk,
            "n_chunks_sped_up": sum(1 for c in per_chunk if c["tempo_applied"] > 1.0),
            "max_tempo": max(c["tempo_applied"] for c in per_chunk),
            "total_cut_tail_s": round(sum(c["cut_tail_s"] for c in per_chunk), 2),
            "n_segments_dropped_by_clamp": dropped, **drift_stats(drifts)}


async def amain() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--variants", default="V2,V4")
    ap.add_argument("--assembly", choices=["old", "new", "both"], default="both")
    ap.add_argument("--only", default="", help="Chỉ kiểm các video id này (phân cách dấu phẩy)")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = (AI_WORKER_ROOT / run_dir).resolve()
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    modes = ["old", "new"] if args.assembly == "both" else [args.assembly]

    with (run_dir / "videos.csv").open(encoding="utf-8-sig", newline="") as fh:
        videos = [r for r in csv.DictReader(fh) if not only or r["video_id"] in only]
    with (run_dir / "segments.csv").open(encoding="utf-8-sig", newline="") as fh:
        branch_of = {(r["video_id"], r["variant"], int(r["chunk_index"]), int(r["seq"])): r["branch"]
                     for r in csv.DictReader(fh)}

    rows_out: list[dict] = []
    result: dict = {"run_id": run_dir.name, "max_chunk_tempo": audio_utils.MAX_CHUNK_TEMPO, "videos": {}}
    with tempfile.TemporaryDirectory(prefix="check_full_length_") as td:
        tmp = Path(td)
        for v in videos:
            vid = v["video_id"]
            cache = json.loads((CACHE_ROOT / vid / "asr_cache.json").read_text(encoding="utf-8"))
            result["videos"][vid] = {}
            for variant in variants:
                result["videos"][vid][variant] = {}
                for mode in modes:
                    print(f"[{vid}] {variant} ({mode}) ...", flush=True)
                    if mode == "old":
                        r = await assemble_old(run_dir, vid, float(v["duration_sec"]), variant, cache, tmp, rows_out)
                    else:
                        r = await assemble_new(run_dir, vid, float(v["duration_sec"]), variant, cache, tmp, rows_out,
                                               branch_of)
                    result["videos"][vid][variant][mode] = r

    (run_dir / "check_full_length.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows_out:
        with (run_dir / "drift_measured.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

    lines = [f"# Kiểm tra ghép toàn bài trên audio thật — run `{run_dir.name}`", "",
             "`old` = cách ghép trước 11/11/2026 (khoảng lặng tương đối); `new` = `audio_utils.place_on_timeline` "
             f"(mốc tuyệt đối, tăng tốc cả đoạn tối đa ×{audio_utils.MAX_CHUNK_TEMPO}, kẹp mốc ASR).",
             "Trễ > 0: tiếng lồng **muộn** hơn mốc gốc; trễ < 0: **sớm** hơn. \"|trễ|\" là giá trị tuyệt đối.", "",
             "| Video | PA | Ghép | Gốc (s) | Sau ghép (s) | Chênh (s) | Trễ TB có dấu | \\|trễ\\| TB | \\|trễ\\| p95 | Muộn max | Sớm max | % \\|trễ\\|>1 s | >2 s | Đoạn tăng tốc | Tempo max | Cắt đuôi (s) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    errs = []
    for vid, per_v in result["videos"].items():
        for variant, per_m in per_v.items():
            for mode, r in per_m.items():
                if "error" in r:
                    errs.append((vid, variant, mode, r["error"]))
                    continue
                lines.append(
                    f"| {vid} | {variant} | {mode} | {r['original_duration_s']} | {r['final_duration_s']} | {r['diff_s']} | "
                    f"{r['drift_signed_mean_s']} | {r['drift_abs_mean_s']} | {r['drift_abs_p95_s']} | {r['drift_max_late_s']} | "
                    f"{r['drift_max_early_s']} | {r['pct_abs_drift_gt_1s']} | {r['pct_abs_drift_gt_2s']} | "
                    f"{r['n_chunks_sped_up']}/{len(r['per_chunk'])} | {r['max_tempo']} | {r['total_cut_tail_s']} |")
    if errs:
        lines += ["", "## Không ghép được", ""] + [f"- {a} {b} ({m}): {c}" for a, b, m, c in errs]
    (run_dir / "check_full_length.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(amain())
