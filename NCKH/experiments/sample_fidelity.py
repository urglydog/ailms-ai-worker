"""Lấy mẫu ngẫu nhiên các câu bị rút gọn (was_summarized) để 2 người chấm độ trung thành nội dung (L4).

Dùng:
    python NCKH/experiments/sample_fidelity.py NCKH/experiments/results/full_r1 --n 50 --seed 42
Xuất vào <run_dir>:
    fidelity_sample.csv  : id, video_id, chunk_index, seq, t_orig, src_text, tgt_v2 (trước rút gọn), tgt_v4 (sau rút gọn)
    fidelity_scores.csv  : id, score_rater1, score_rater2 (để trống cho người chấm điền; 2=đủ ý, 1=mất ý phụ, 0=mất/sai ý chính)
Người chấm nên nhận bản sao RIÊNG của file mẫu, chấm độc lập, không trao đổi trước khi nộp.
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--variant", default="V4")
    ap.add_argument("--baseline", default="V2", help="Phương án dùng làm bản dịch 'trước rút gọn'")
    ap.add_argument("--min-frame", type=float, default=0.0,
                    help="Chỉ lấy câu có khung gốc t_orig >= giá trị này (giây). Pipeline sau 11/11/2026 không rút gọn "
                         "câu có khung < 2 s (MIN_RESUMMARIZE_FRAME_SEC), nên dùng --min-frame 2.0 để mẫu chỉ gồm câu vẫn bị rút gọn.")
    ap.add_argument("--out-suffix", default="", help="Hậu tố tên file đầu ra, vd _v2 -> fidelity_sample_v2.csv")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)

    with (run_dir / "segments.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    key = lambda r: (r["video_id"], int(r["chunk_index"]), int(r["seq"]))
    base = {key(r): r for r in rows if r["variant"] == args.baseline}
    pool = [r for r in rows if r["variant"] == args.variant and r["was_summarized"] == "True"
            and float(r["t_orig"]) >= args.min_frame]
    pool.sort(key=key)  # thứ tự cố định trước khi lấy mẫu -> tái lập được với cùng seed
    if len(pool) < args.n:
        print(f"Cảnh báo: chỉ có {len(pool)} câu rút gọn, nhỏ hơn --n {args.n}; lấy hết.")
    picked = random.Random(args.seed).sample(pool, min(args.n, len(pool)))

    sample_path = run_dir / f"fidelity_sample{args.out_suffix}.csv"
    with sample_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "video_id", "chunk_index", "seq", "t_orig", "src_text", "tgt_v2", "tgt_v4"])
        for i, r in enumerate(picked, 1):
            b = base.get(key(r), {})
            w.writerow([i, r["video_id"], r["chunk_index"], r["seq"], r["t_orig"],
                        r["src_text"], b.get("tgt_text", ""), r["tgt_text"]])

    scores_path = run_dir / f"fidelity_scores{args.out_suffix}.csv"
    with scores_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "score_rater1", "score_rater2"])
        for i in range(1, len(picked) + 1):
            w.writerow([i, "", ""])
    print(f"Pool {len(pool)} câu rút gọn; đã lấy {len(picked)} (seed={args.seed}).")
    print(f"-> {sample_path}\n-> {scores_path}")


if __name__ == "__main__":
    main()
