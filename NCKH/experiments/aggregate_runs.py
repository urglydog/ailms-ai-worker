"""Gộp nhiều lần chạy (full_r1, full_r2, ...) -> trung bình ± độ lệch chuẩn mẫu (n-1) của từng chỉ số.

Dùng (L3):
    python NCKH/experiments/aggregate_runs.py NCKH/experiments/results/full_r1 \
        NCKH/experiments/results/full_r2 NCKH/experiments/results/full_r3 --out NCKH/experiments/results/aggregate_full
Mỗi run cần có summary.json (chạy analyze.py trước). Chỉ gộp phương án có mặt ở ít nhất 1 run; số run
dùng để tính được ghi ở cột n_runs (V1/V3 thường chỉ có ở full_r1 -> n_runs=1, không có độ lệch chuẩn).
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

METRICS = [
    ("mean_abs_delta_s", "Δ TB (s)"),
    ("median_abs_delta_s", "Δ trung vị (s)"),
    ("p95_abs_delta_s", "Δ p95 (s)"),
    ("pct_segments_overrun", "% câu còn tràn"),
    ("pct_segments_R_gt_1_3_after", "% R>1,3 sau"),
    ("total_overrun_s", "Tổng thời gian tràn (s)"),
    ("llm_calls", "LLM"),
    ("tts_calls", "TTS"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", required=True, help="Tiền tố file đầu ra (.json và .md)")
    args = ap.parse_args()

    per_run: dict[str, dict] = {}
    for r in args.runs:
        p = Path(r) / "summary.json"
        per_run[Path(r).name] = json.loads(p.read_text(encoding="utf-8"))["variants"]

    variants = sorted({v for vs in per_run.values() for v in vs})
    result: dict[str, dict] = {}
    for v in variants:
        runs_with = [name for name, vs in per_run.items() if v in vs]
        row: dict = {"n_runs": len(runs_with), "runs": runs_with}
        for key, _ in METRICS:
            xs = [float(per_run[name][v][key]) for name in runs_with if key in per_run[name][v]]
            if not xs:
                continue
            row[key] = {
                "mean": round(st.mean(xs), 3),
                "sd": round(st.stdev(xs), 3) if len(xs) >= 2 else None,
                "values": [round(x, 3) for x in xs],
            }
        result[v] = row

    Path(args.out + ".json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    def cell(m: dict | None) -> str:
        if not m:
            return "–"
        return f"{m['mean']} ± {m['sd']}" if m["sd"] is not None else f"{m['mean']} (n=1)"

    lines = ["# Gộp các lần chạy", "", f"Runs: {', '.join(per_run)}", "",
             "Trung bình ± độ lệch chuẩn mẫu (n−1); chỉ có độ lệch chuẩn khi phương án có ≥2 run.", "",
             "| Phương án | n_runs | " + " | ".join(label for _, label in METRICS) + " |",
             "|---|---|" + "---|" * len(METRICS)]
    for v, row in result.items():
        lines.append(f"| {v} | {row['n_runs']} | " + " | ".join(cell(row.get(k)) for k, _ in METRICS) + " |")
    Path(args.out + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
