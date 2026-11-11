"""MÔ PHỎNG (không gọi API, không đổi code app): nếu ghép câu theo MỐC TUYỆT ĐỐI thì độ trễ so với video gốc còn bao nhiêu?

Hiện tại pipeline chèn khoảng lặng TƯƠNG ĐỐI (start - prev_end của bản gốc) nên câu tràn làm các câu sau trễ dần
(xem drift_analysis.py / check_full_length.py). Mô phỏng này giữ nguyên câu dịch và độ dài giọng đọc, chỉ đổi cách xếp:
    onset_i = max(start_i, thời điểm câu trước kết thúc);  trễ_i = onset_i - start_i
Độ dài giọng đọc = t_final, riêng nhánh `pad` dùng t_tts_default (bỏ phần đệm lặng vì không còn cần).
Mốc `start` đọc từ .cache/<video>/asr_cache.json (cùng thư mục experiments). Kết quả là ƯỚC LƯỢNG, chưa phải audio thật.

Dùng:
    python NCKH/experiments/simulate_resync.py NCKH/experiments/results/full_r1 --variants V2,V4
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

CACHE_ROOT = Path(__file__).parent / ".cache"


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))] if s else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--variants", default="V2,V4")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]

    with (run_dir / "segments.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["variant"] in variants:
            groups[(r["variant"], r["video_id"])].append(r)

    out: dict[str, dict] = {}
    lines = ["| Phương án | Video | Trễ TB (s) | p95 (s) | max (s) | % câu trễ >1 s | >2 s | max khi đồng bộ lại mỗi đoạn (s) |",
             "|---|---|---|---|---|---|---|---|"]
    for (variant, vid), rs in sorted(groups.items()):
        cache = json.loads((CACHE_ROOT / vid / "asr_cache.json").read_text(encoding="utf-8"))
        seg = {(int(ci), s["seq"]): s for ci, ss in cache["chunks"].items() for s in ss}
        rs.sort(key=lambda r: (int(r["chunk_index"]), int(r["seq"])))

        def dur(r: dict) -> float:
            return float(r["t_tts_default"]) if r["branch"] == "pad" else float(r["t_final"])

        pos, drift = 0.0, []
        for r in rs:
            s = seg[(int(r["chunk_index"]), int(r["seq"]))]
            onset = max(s["start"], pos)
            drift.append(onset - s["start"])
            pos = onset + dur(r)

        pos, cur, drift_reset = 0.0, None, []
        for r in rs:
            ci = int(r["chunk_index"])
            s = seg[(ci, int(r["seq"]))]
            if ci != cur:
                cur, pos = ci, ci * float(cache["chunk_minutes"]) * 60.0
            onset = max(s["start"], pos)
            drift_reset.append(onset - s["start"])
            pos = onset + dur(r)

        n = len(drift)
        res = {
            "n": n, "mean_s": round(st.mean(drift), 2), "p95_s": round(p95(drift), 2), "max_s": round(max(drift), 2),
            "pct_gt_1s": round(100 * sum(x > 1 for x in drift) / n, 1),
            "pct_gt_2s": round(100 * sum(x > 2 for x in drift) / n, 1),
            "max_reset_each_chunk_s": round(max(drift_reset), 2),
        }
        out[f"{variant}|{vid}"] = res
        lines.append(f"| {variant} | {vid} | {res['mean_s']} | {res['p95_s']} | {res['max_s']} | {res['pct_gt_1s']} | "
                     f"{res['pct_gt_2s']} | {res['max_reset_each_chunk_s']} |")

    (run_dir / "simulate_resync.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Mô phỏng xếp câu theo mốc tuyệt đối (ước lượng, không phải audio thật)", ""] + lines
    (run_dir / "simulate_resync.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
