"""Ước lượng ĐỘ TRỄ CỘNG DỒN của âm thanh lồng tiếng so với video gốc, từ segments.csv.

Vì sao cần: chỉ số Δ = |t_final - t_orig| (analyze.py) đo độ lệch của TỪNG câu, nhưng không phản ánh việc
các câu sau bị đẩy trễ dần. Trong pipeline (dubbing_service.py), khoảng lặng trước mỗi câu là
`seg.start - prev_end` của bản GỐC (cố định) và câu được chèn nguyên độ dài, nên câu nào đọc dài hơn khung
`t_orig` sẽ làm mọi câu sau đó trễ thêm đúng phần dư, không được bù lại.

Mô hình (giả định — cần đối chiếu với audio ghép thật bằng check_full_length / re-ASR):
    d_j        = t_final_j - t_orig_j            (câu ngắn hơn khung ở nhánh R<=1 được đệm lặng nên d=0;
                                                  câu tăng tốc có thể ngắn hơn khung chút ít nên d hơi âm —
                                                  giữ nguyên dấu; min_d_s trong kết quả cho biết mức âm lớn nhất)
    trễ trong đoạn tại câu i   = sum_{j<i, cùng đoạn} d_j
    trễ cuối đoạn              = sum_{j trong đoạn} d_j
    trễ tích lũy (có nối đoạn) = trễ trong đoạn + tổng trễ cuối đoạn của các đoạn trước

Dùng:
    python NCKH/experiments/drift_analysis.py NCKH/experiments/results/full_r1
Xuất: <run_dir>/drift_summary.json, <run_dir>/drift_summary.md
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def analyze_group(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda r: (int(r["chunk_index"]), int(r["seq"])))
    carry = 0.0                      # trễ cuối của các đoạn trước
    onset_in_chunk: list[float] = []
    onset_cum: list[float] = []
    chunk_end: dict[int, float] = {}
    cur_chunk = None
    run = 0.0
    min_d = 0.0
    for r in rows:
        ci = int(r["chunk_index"])
        if cur_chunk is None:
            cur_chunk = ci
        if ci != cur_chunk:
            chunk_end[cur_chunk] = run
            carry += run
            run = 0.0
            cur_chunk = ci
        onset_in_chunk.append(run)
        onset_cum.append(carry + run)
        d = float(r["t_final"]) - float(r["t_orig"])
        min_d = min(min_d, d)
        run += d
    if cur_chunk is not None:
        chunk_end[cur_chunk] = run
        carry += run
    n = len(onset_cum)

    def frac(xs: list[float], thr: float) -> float:
        return round(100.0 * sum(1 for x in xs if x > thr) / n, 1) if n else 0.0

    return {
        "n_segments": n,
        "n_chunks": len(chunk_end),
        "chunk_end_drift_s": {str(k): round(v, 2) for k, v in sorted(chunk_end.items())},
        "chunk_end_drift_mean_s": round(st.mean(chunk_end.values()), 2) if chunk_end else 0.0,
        "chunk_end_drift_max_s": round(max(chunk_end.values()), 2) if chunk_end else 0.0,
        "total_drift_end_of_video_s": round(carry, 2),
        "onset_in_chunk_mean_s": round(st.mean(onset_in_chunk), 2) if n else 0.0,
        "onset_in_chunk_p95_s": round(p95(onset_in_chunk), 2),
        "onset_in_chunk_max_s": round(max(onset_in_chunk), 2) if n else 0.0,
        "onset_cumulative_mean_s": round(st.mean(onset_cum), 2) if n else 0.0,
        "onset_cumulative_p95_s": round(p95(onset_cum), 2),
        "onset_cumulative_max_s": round(max(onset_cum), 2) if n else 0.0,
        "pct_sentences_cum_drift_gt_0_5s": frac(onset_cum, 0.5),
        "pct_sentences_cum_drift_gt_1s": frac(onset_cum, 1.0),
        "pct_sentences_cum_drift_gt_2s": frac(onset_cum, 2.0),
        "min_d_s": round(min_d, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    seg = read_csv(run_dir / "segments.csv")

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in seg:
        groups[(r["variant"], r["video_id"])].append(r)

    per_video = {f"{v}|{vid}": analyze_group(rows) for (v, vid), rows in sorted(groups.items())}

    per_variant: dict[str, dict] = {}
    for variant in sorted({k[0] for k in groups}):
        vids = [per_video[f"{variant}|{vid}"] for (v, vid) in groups if v == variant]
        per_variant[variant] = {
            "n_videos": len(vids),
            "total_drift_end_of_video_s_mean": round(st.mean(x["total_drift_end_of_video_s"] for x in vids), 2),
            "total_drift_end_of_video_s_max": round(max(x["total_drift_end_of_video_s"] for x in vids), 2),
            "chunk_end_drift_mean_s": round(st.mean(x["chunk_end_drift_mean_s"] for x in vids), 2),
            "chunk_end_drift_max_s": round(max(x["chunk_end_drift_max_s"] for x in vids), 2),
            "onset_cumulative_p95_s_max_over_videos": round(max(x["onset_cumulative_p95_s"] for x in vids), 2),
        }

    out = {
        "run_id": run_dir.name,
        "model_note": "Ước lượng từ segments.csv dưới giả định khoảng lặng cố định (xem docstring); "
                      "cần kiểm chứng bằng audio ghép thật.",
        "per_variant": per_variant,
        "per_video": per_video,
    }
    (run_dir / "drift_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"# Độ trễ cộng dồn ước lượng — run `{run_dir.name}`", "",
             "_Ước lượng từ `segments.csv` (mô hình trong `drift_analysis.py`); chưa phải số đo trên audio thật._", "",
             "## Theo phương án (trung bình/lớn nhất trên các video)", "",
             "| Phương án | Trễ cuối video TB (s) | Trễ cuối video max (s) | Trễ cuối đoạn TB (s) | Trễ cuối đoạn max (s) |",
             "|---|---|---|---|---|"]
    for v, x in per_variant.items():
        lines.append(f"| {v} | {x['total_drift_end_of_video_s_mean']} | {x['total_drift_end_of_video_s_max']} | "
                     f"{x['chunk_end_drift_mean_s']} | {x['chunk_end_drift_max_s']} |")
    lines += ["", "## Theo video", "",
              "| Phương án | Video | Đoạn | Trễ cuối video (s) | Trễ cuối đoạn max (s) | % câu trễ cộng dồn >1 s | >2 s |",
              "|---|---|---|---|---|---|---|"]
    for key, x in per_video.items():
        v, vid = key.split("|")
        lines.append(f"| {v} | {vid} | {x['n_chunks']} | {x['total_drift_end_of_video_s']} | "
                     f"{x['chunk_end_drift_max_s']} | {x['pct_sentences_cum_drift_gt_1s']} | "
                     f"{x['pct_sentences_cum_drift_gt_2s']} |")
    (run_dir / "drift_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
