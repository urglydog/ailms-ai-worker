"""MOS (L5) bước 2 — ghép clip có hình để người nghe chấm: V2 và V4 của mỗi đoạn, tên file ngẫu nhiên.

Với mỗi đoạn trong clips_plan.csv và mỗi phương án (V2, V4):
  - ghép audio lồng tiếng của đúng các câu trong đoạn bằng CÙNG hàm của pipeline (audio_utils.place_on_timeline,
    mốc tuyệt đối, khớp đúng độ dài đoạn) — hai phương án được ghép giống hệt nhau, chỉ khác bản dịch/tốc độ;
  - cắt video gốc đúng khoảng [start, end] và ghép audio lồng tiếng vào (video gốc bị tắt tiếng).
Xuất mp4 tên ngẫu nhiên (C###.mp4) vào --out-dir và results/mos/clips_key.csv (mã clip -> đoạn, phương án).
KHÔNG gửi clips_key.csv cho người nghe. KHÔNG commit mp4 (đã thêm vào .gitignore).

Chạy TRONG container ai-worker bằng user thường; video gốc đặt trong thư mục --video-dir với tên <video_id>.mp4
(tải trên máy Thiện bằng yt-dlp; IP server bị YouTube chặn), rồi copy vào thư mục bind-mount (vd NCKH/experiments/media/):
    docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/mos_make_clips.py \
        NCKH/experiments/results/post_fix_r1 --video-dir NCKH/experiments/media --out-dir NCKH/experiments/results/mos/clips
Video chỉ dùng nội bộ để chấm điểm, không đăng công khai.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import random
import subprocess
import sys
import tempfile
from pathlib import Path

AI_WORKER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_WORKER_ROOT))

from app import audio_utils  # noqa: E402

EXP = Path(__file__).parent


async def build_dub(run_dir: Path, plan_row: dict, variant: str, seg_chunk: dict, starts: dict, tmp: Path) -> Path:
    vid = plan_row["video_id"]
    seqs = [int(x) for x in plan_row["seqs"].split()]
    win_start = float(plan_row["start_sec"])
    length = float(plan_row["end_sec"]) - win_start
    paths, desired = [], []
    for seq in seqs:
        f = run_dir / "audio" / vid / f"c{seg_chunk[(vid, seq)]}_s{seq}_{variant.lower()}.mp3"
        if not f.exists():
            raise FileNotFoundError(f"Thiếu file câu {f} (run cần chạy với --keep-audio)")
        paths.append(f)
        desired.append(max(0.0, starts[(vid, seq)] - win_start))
    out = tmp / f"{plan_row['window_id']}_{variant}.mp3"
    await audio_utils.place_on_timeline(paths, desired, length, out)
    return out


async def amain() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--plan", default=str(EXP / "results" / "mos" / "clips_plan.csv"))
    ap.add_argument("--video-dir", required=True)
    ap.add_argument("--out-dir", default=str(EXP / "results" / "mos" / "clips"))
    ap.add_argument("--variants", default="V2,V4")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    root = AI_WORKER_ROOT
    run_dir = Path(args.run_dir) if Path(args.run_dir).is_absolute() else (root / args.run_dir)
    plan_path, video_dir, out_dir = (Path(p) if Path(p).is_absolute() else root / p
                                     for p in (args.plan, args.video_dir, args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]

    with plan_path.open(encoding="utf-8-sig", newline="") as fh:
        plan = list(csv.DictReader(fh))
    with (run_dir / "segments.csv").open(encoding="utf-8-sig", newline="") as fh:
        seg_chunk = {(r["video_id"], int(r["seq"])): int(r["chunk_index"]) for r in csv.DictReader(fh)}
    import json
    starts: dict[tuple[str, int], float] = {}
    for vid in {p["video_id"] for p in plan}:
        cache = json.loads((EXP / ".cache" / vid / "asr_cache.json").read_text(encoding="utf-8"))
        for ss in cache["chunks"].values():
            for s in ss:
                starts[(vid, s["seq"])] = s["start"]

    jobs = [(p, v) for p in plan for v in variants]
    rng = random.Random(args.seed)
    codes = rng.sample(range(100, 1000), len(jobs))
    key_rows = []
    with tempfile.TemporaryDirectory(prefix="mos_clips_") as td:
        tmp = Path(td)
        for (p, v), code in zip(jobs, codes):
            video = video_dir / f"{p['video_id']}.mp4"
            if not video.exists():
                raise FileNotFoundError(f"Thiếu video gốc {video}")
            dub = await build_dub(run_dir, p, v, seg_chunk, starts, tmp)
            clip = out_dir / f"C{code}.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", p["start_sec"], "-to", p["end_sec"], "-i", str(video),
                            "-i", str(dub), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-shortest", str(clip)], check=True)
            key_rows.append({"clip_code": f"C{code}", "window_id": p["window_id"], "video_id": p["video_id"], "variant": v})
            print(f"{clip.name}  <- {p['window_id']} {v}", flush=True)

    key_rows.sort(key=lambda r: r["clip_code"])
    key_path = plan_path.with_name("clips_key.csv")
    with key_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["clip_code", "window_id", "video_id", "variant"])
        w.writeheader()
        w.writerows(key_rows)
    print(f"Xong {len(key_rows)} clip -> {out_dir}; bảng giải mã (KHÔNG gửi người nghe): {key_path}")


if __name__ == "__main__":
    asyncio.run(amain())
