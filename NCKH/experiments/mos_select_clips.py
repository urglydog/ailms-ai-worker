"""MOS (L5) bước 1 — chọn 20 đoạn (mặc định 5 đoạn/bài) dài 15–25 giây, nhiều câu liên tiếp, phân tầng theo nhánh xử lý.

Mỗi đoạn nằm trọn trong 1 chunk 10 phút, không chồng nhau. Ưu tiên đoạn chứa câu ở nhánh speedup / summarize / capped /
câu ngắn (khung < 2 s) / pad, mỗi nhánh được đại diện trước, phần còn lại lấp bằng đoạn "thú vị" ngẫu nhiên (seed cố định).

Dùng (chạy được bằng Python thường, chỉ thư viện chuẩn):
    python3 NCKH/experiments/mos_select_clips.py NCKH/experiments/results/post_fix_r1 --seed 42
Cần run_dir/segments.csv (V4, có cột branch) và .cache/<video>/asr_cache.json.
Ghi: NCKH/experiments/results/mos/clips_plan.csv
Lưu ý: nhánh lấy từ run bạn truyền vào — dùng run CHẠY SAU bản sửa 11/11 (pipeline mới) để phân tầng đúng.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

CACHE_ROOT = Path(__file__).parent / ".cache"
CATEGORIES = ["speedup", "summarize", "capped", "short", "pad"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--variant", default="V4")
    ap.add_argument("--per-video", type=int, default=5)
    ap.add_argument("--min-len", type=float, default=15.0)
    ap.add_argument("--max-len", type=float, default=25.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).parent / "results" / "mos" / "clips_plan.csv"))
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    rng = random.Random(args.seed)

    with (run_dir / "segments.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["variant"] == args.variant]
    branch = {(r["video_id"], int(r["chunk_index"]), int(r["seq"])): r["branch"] for r in rows}
    videos = sorted({r["video_id"] for r in rows})

    plan = []
    for vid in videos:
        cache = json.loads((CACHE_ROOT / vid / "asr_cache.json").read_text(encoding="utf-8"))
        cands = []
        for ci, ss in cache["chunks"].items():
            ci = int(ci)
            ss = [s for s in sorted(ss, key=lambda s: s["seq"]) if (vid, ci, s["seq"]) in branch]
            for i in range(len(ss)):
                for j in range(i, len(ss)):
                    length = ss[j]["end"] - ss[i]["start"]
                    if length > args.max_len:
                        break
                    if length >= args.min_len and j > i:
                        win = ss[i:j + 1]
                        tags = {branch[(vid, ci, s["seq"])] for s in win}
                        if any(s["end"] - s["start"] < 2.0 for s in win):
                            tags.add("short")
                        cands.append({"video_id": vid, "chunk": ci, "start": ss[i]["start"], "end": ss[j]["end"],
                                      "seqs": [s["seq"] for s in win], "tags": tags})
                        break
        rng.shuffle(cands)
        chosen: list[dict] = []

        def free(c: dict) -> bool:
            return all(c["end"] <= x["start"] or c["start"] >= x["end"] for x in chosen)

        for cat in CATEGORIES:
            if len(chosen) >= args.per_video:
                break
            if any(cat in x["tags"] for x in chosen):
                continue
            for c in cands:
                if cat in c["tags"] and free(c):
                    chosen.append(c)
                    break
        for c in cands:
            if len(chosen) >= args.per_video:
                break
            if c not in chosen and free(c):
                chosen.append(c)
        chosen.sort(key=lambda c: c["start"])
        for k, c in enumerate(chosen, 1):
            plan.append({"window_id": f"{vid}_w{k}", **c})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["window_id", "video_id", "chunk", "start_sec", "end_sec", "length_sec", "n_sentences", "seqs", "branches"])
        for p in plan:
            w.writerow([p["window_id"], p["video_id"], p["chunk"], round(p["start"], 2), round(p["end"], 2),
                        round(p["end"] - p["start"], 1), len(p["seqs"]), " ".join(map(str, p["seqs"])),
                        " ".join(sorted(p["tags"]))])
    per = defaultdict(int)
    for p in plan:
        per[p["video_id"]] += 1
    print(f"Đã chọn {len(plan)} đoạn (seed={args.seed}): {dict(per)} -> {out}")


if __name__ == "__main__":
    main()
