"""Tổng hợp kết quả của run_experiment.py thành số liệu để điền vào bài báo.

Chỉ dùng thư viện chuẩn (không cần pandas). matplotlib là tùy chọn: nếu có thì vẽ
thêm biểu đồ phân bố R (figures/r_hist.pdf) để chèn vào main.tex.

    python NCKH/experiments/analyze.py NCKH/experiments/results/<run_id>
    python NCKH/experiments/analyze.py <run_dir> --server NCKH/experiments/results/server_<ngày>

In ra:
  1. Bảng so sánh 4 phương án (Δ trung bình, tràn thời lượng, tỷ lệ R>1.3, số lần gọi LLM)
     + các dòng LaTeX dán thẳng vào Bảng tab:results.
  2. Phân bố nhánh xử lý của phương án đề xuất (V4).
  3. Thời gian xử lý / phút video (local) và, nếu có, số liệu từ server.
Toàn bộ cũng được ghi vào <run_dir>/summary.md và summary.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

NAMES = {
    "V1": "Dịch một pha, tốc độ mặc định",
    "V2": "Dịch hai pha, tốc độ mặc định",
    "V3": "Hai pha + tăng tốc độ đọc",
    "V4": "Đề xuất (đầy đủ)",
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def pct(a: int, b: int) -> float:
    return 100.0 * a / b if b else 0.0


def p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]


def summarize_variants(seg: list[dict], videos: list[dict]) -> dict:
    by_v: dict[str, list[dict]] = defaultdict(list)
    for r in seg:
        by_v[r["variant"]].append(r)

    # Số lời gọi LLM của pha dịch: V1 dùng 1 lời gọi/chunk, V2-V4 dùng 2 lời gọi/chunk.
    llm_translate = sum(int(f(v["llm_calls_translate"])) for v in videos)
    out = {}
    for v in ["V1", "V2", "V3", "V4"]:
        rows = by_v.get(v, [])
        if not rows:
            continue
        deltas = [f(r["abs_delta"]) for r in rows]
        overrun = [f(r["overrun"]) for r in rows]
        t_orig = sum(f(r["t_orig"]) for r in rows)
        n = len(rows)
        # với V1/V2/V3, "R>1.3 còn lại" là câu vẫn tràn sau xử lý; với V4 tính theo t_final
        over_13 = sum(1 for r in rows if f(r["t_final"]) > 1.3 * f(r["t_orig"]) + 1e-6)
        still_over = sum(1 for r in rows if f(r["overrun"]) > 0.05)
        extra_llm = sum(int(f(r["llm_calls"])) for r in rows)
        base_llm = llm_translate // 2 if v == "V1" else llm_translate
        out[v] = {
            "name": NAMES[v],
            "n_segments": n,
            "mean_abs_delta_s": round(st.mean(deltas), 3),
            "median_abs_delta_s": round(st.median(deltas), 3),
            "p95_abs_delta_s": round(p95(deltas), 3),
            "total_overrun_s": round(sum(overrun), 1),
            "overrun_per_min_speech_s": round(sum(overrun) / (t_orig / 60), 2) if t_orig else 0.0,
            "pct_segments_overrun": round(pct(still_over, n), 1),
            "pct_segments_R_gt_1_3_after": round(pct(over_13, n), 1),
            "pct_R_default_gt_1_3": round(pct(sum(1 for r in rows if f(r["r_default"]) > 1.3), n), 1),
            "mean_R_default": round(st.mean(f(r["r_default"]) for r in rows), 3),
            "llm_calls": base_llm + extra_llm,
            "tts_calls": sum(int(f(r["tts_calls"])) for r in rows),
            "mean_chars": round(st.mean(f(r["tgt_chars"]) for r in rows), 1),
        }
    return out


def branch_distribution(seg: list[dict]) -> dict:
    out = {}
    for v in ["V1", "V2", "V3", "V4"]:
        rows = [r for r in seg if r["variant"] == v]
        if not rows:
            continue
        c = Counter(r["branch"] for r in rows)
        out[v] = {k: {"n": n, "pct": round(pct(n, len(rows)), 1)} for k, n in c.most_common()}
        # phân bố R mặc định theo 3 vùng của công thức (eq:policy)
        rs = [f(r["r_default"]) for r in rows]
        out[v]["_R_zones"] = {
            "R<=1.0": round(pct(sum(1 for x in rs if x <= 1.0), len(rs)), 1),
            "1.0<R<=1.3": round(pct(sum(1 for x in rs if 1.0 < x <= 1.3), len(rs)), 1),
            "R>1.3": round(pct(sum(1 for x in rs if x > 1.3), len(rs)), 1),
        }
    return out


def local_timing(videos: list[dict]) -> dict:
    if not videos:
        return {}
    minutes = sum(f(v["duration_sec"]) for v in videos) / 60 or 1
    asr_live = [v for v in videos if str(v.get("asr_cached")).lower() != "true"]
    asr_min = sum(f(v["duration_sec"]) for v in asr_live) / 60
    return {
        "n_videos": len(videos),
        "total_minutes": round(minutes, 1),
        "asr_sec_per_min": round(sum(f(v["t_asr_sec"]) for v in asr_live) / asr_min, 2) if asr_min else None,
        "translate_sec_per_min": round(sum(f(v["t_translate_sec"]) for v in videos) / minutes, 2),
        "tts_default_sec_per_min": round(sum(f(v["t_tts_default_sec"]) for v in videos) / minutes, 2),
        "v4_adaptive_sec_per_min": round(sum(f(v["t_v4_sec"]) for v in videos) / minutes, 2),
        "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats.",
    }


def server_timing(server_dir: Path) -> dict:
    jobs = [j for j in read_csv(server_dir / "jobs.csv") if j.get("status") == "COMPLETED"]
    if not jobs:
        return {}
    spm = [f(j["processing_sec"]) / (f(j["lesson_duration_sec"]) / 60) for j in jobs if f(j["lesson_duration_sec"]) > 0]
    first = [f(j["first_chunk_sec"]) for j in jobs if j.get("first_chunk_sec") not in ("", None)]
    return {
        "n_jobs": len(jobs),
        "processing_sec_per_video_min_mean": round(st.mean(spm), 2) if spm else None,
        "processing_sec_per_video_min_median": round(st.median(spm), 2) if spm else None,
        "first_chunk_sec_mean": round(st.mean(first), 1) if first else None,
        "first_chunk_sec_median": round(st.median(first), 1) if first else None,
    }


def latex_rows(variants: dict) -> str:
    lines = []
    for v, d in variants.items():
        lines.append(
            f"{d['name']} & {d['mean_abs_delta_s']:.2f} & {d['pct_segments_R_gt_1_3_after']:.1f}\\% & {d['llm_calls']} \\\\"
        )
    return "\n".join(lines)


def maybe_plot(seg: list[dict], out: Path) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(3.5, 2.3))
    for v, label in [("V1", "Một pha"), ("V2", "Hai pha")]:
        rs = [min(f(r["r_default"]), 2.5) for r in seg if r["variant"] == v]
        if rs:
            ax.hist(rs, bins=30, alpha=0.55, label=label)
    for x in (1.0, 1.3):
        ax.axvline(x, color="k", ls="--", lw=0.8)
    ax.set_xlabel("R = T_tts / T_orig")
    ax.set_ylabel("Số câu")
    ax.legend(fontsize=7)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    return str(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--server", default="", help="Thư mục kết quả của server_job_stats.py (tùy chọn)")
    args = ap.parse_args()
    run = Path(args.run_dir)

    seg = read_csv(run / "segments.csv")
    videos = read_csv(run / "videos.csv")
    if not seg:
        raise SystemExit(f"Không thấy {run / 'segments.csv'}")

    summary = {
        "variants": summarize_variants(seg, videos),
        "branches": branch_distribution(seg),
        "local_timing": local_timing(videos),
        "server_timing": server_timing(Path(args.server)) if args.server else {},
    }
    fig = maybe_plot(seg, run / "figures" / "r_hist.pdf")

    md = ["# Tóm tắt thực nghiệm", "", f"Run: `{run.name}`", "",
          "## Bảng so sánh phương án", "",
          "| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |",
          "|---|---|---|---|---|---|---|---|---|"]
    for d in summary["variants"].values():
        md.append(f"| {d['name']} | {d['n_segments']} | {d['mean_abs_delta_s']} | {d['median_abs_delta_s']} | "
                  f"{d['p95_abs_delta_s']} | {d['pct_segments_overrun']} | {d['pct_segments_R_gt_1_3_after']} | "
                  f"{d['llm_calls']} | {d['tts_calls']} |")
    md += ["", "### Dòng LaTeX cho Bảng tab:results", "", "```latex", latex_rows(summary["variants"]), "```", "",
           "## Phân bố nhánh xử lý", "", "```json", json.dumps(summary["branches"], ensure_ascii=False, indent=1), "```",
           "", "## Thời gian (local)", "", "```json", json.dumps(summary["local_timing"], ensure_ascii=False, indent=1), "```"]
    if summary["server_timing"]:
        md += ["", "## Thời gian (server)", "", "```json",
               json.dumps(summary["server_timing"], ensure_ascii=False, indent=1), "```"]
    if fig:
        md += ["", f"Biểu đồ: `{fig}`"]

    (run / "summary.md").write_text("\n".join(md), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
