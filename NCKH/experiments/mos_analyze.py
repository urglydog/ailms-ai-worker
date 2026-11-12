"""MOS (L5) bước 3 — phân tích phiếu chấm: MOS ± KTC 95% cho V2 và V4, kiểm định Wilcoxon theo cặp (theo đoạn).

Đầu vào (đã ẩn danh, mã người nghe P01, P02…, KHÔNG thu thập tên/email):
  --responses : CSV dạng dài: participant,clip_code,naturalness,intelligibility,sync   (thang 1–5; ô trống = bỏ qua)
  --key       : results/mos/clips_key.csv (clip_code, window_id, video_id, variant)
Dùng:
    python3 NCKH/experiments/mos_analyze.py --responses NCKH/experiments/results/mos/mos_responses.csv
Ghi: results/mos/mos_summary.md / .json (cạnh file responses).

Cách tính:
  - MOS mỗi phương án = trung bình của "điểm trung bình theo người nghe" (mỗi người 1 giá trị); KTC 95% theo phân phối t
    (n−1 bậc tự do, bảng cố định, 1,96 nếu n > 31).
  - Wilcoxon theo cặp: với mỗi đoạn lấy trung bình điểm các người nghe cho V2 và V4, d = V4 − V2; bỏ d=0;
    p hai phía CHÍNH XÁC (đếm tổng hạng bằng quy hoạch động, hạng trung bình khi hòa).
  - Người nghe chấm toàn một mức cho mọi clip ở mọi tiêu chí bị loại và được liệt kê (đủ ≥ 2 clip mới xét).
Chỉ dùng thư viện chuẩn (scipy chưa cài trong container).
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
       11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
       21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}
CRITERIA = [("naturalness", "Độ tự nhiên"), ("intelligibility", "Độ dễ hiểu"), ("sync", "Độ khớp hình")]


def ci95(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        return (st.mean(xs) if xs else float("nan"), float("nan"))
    t = T95.get(n - 1, 1.96)
    return (st.mean(xs), t * st.stdev(xs) / (n ** 0.5))


def wilcoxon_exact(d: list[float]) -> dict:
    d = [x for x in d if x != 0]
    n = len(d)
    if n == 0:
        return {"n": 0, "p": None, "w_plus": None}
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    r2 = [int(round(r * 2)) for r in ranks]          # hạng nhân đôi -> số nguyên (hạng trung bình là .5)
    total = sum(r2)
    w2 = sum(r for r, x in zip(r2, d) if x > 0)
    counts = [0] * (total + 1)
    counts[0] = 1
    for r in r2:
        for s in range(total, r - 1, -1):
            counts[s] += counts[s - r]
    all_ = 2 ** n
    p_le = sum(counts[: w2 + 1]) / all_
    p_ge = sum(counts[w2:]) / all_
    return {"n": n, "w_plus": w2 / 2, "p": min(1.0, 2 * min(p_le, p_ge))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--responses", required=True)
    ap.add_argument("--key", default="")
    args = ap.parse_args()
    resp_path = Path(args.responses)
    key_path = Path(args.key) if args.key else resp_path.with_name("clips_key.csv")
    with key_path.open(encoding="utf-8-sig", newline="") as fh:
        key = {r["clip_code"]: r for r in csv.DictReader(fh)}
    with resp_path.open(encoding="utf-8-sig", newline="") as fh:
        resp = list(csv.DictReader(fh))

    def val(x: str) -> float | None:
        x = (x or "").strip()
        return float(x) if x else None

    by_p: dict[str, list[dict]] = defaultdict(list)
    for r in resp:
        if r["clip_code"] in key:
            by_p[r["participant"]].append(r)
    excluded = []
    for p, rs in list(by_p.items()):
        vals = {val(r[c]) for r in rs for c, _ in CRITERIA if val(r[c]) is not None}
        if len(rs) >= 2 and len(vals) == 1:
            excluded.append({"participant": p, "reason": "chấm toàn một mức"})
            del by_p[p]

    out: dict = {"n_participants": len(by_p), "excluded": excluded, "criteria": {}}
    for crit, label in CRITERIA:
        per_var_part: dict[str, list[float]] = {"V2": [], "V4": []}
        win_scores: dict[tuple[str, str], list[float]] = defaultdict(list)
        for p, rs in by_p.items():
            mine: dict[str, list[float]] = defaultdict(list)
            for r in rs:
                v = val(r[crit])
                if v is None:
                    continue
                k = key[r["clip_code"]]
                mine[k["variant"]].append(v)
                win_scores[(k["window_id"], k["variant"])].append(v)
            for var in per_var_part:
                if mine.get(var):
                    per_var_part[var].append(st.mean(mine[var]))
        windows = sorted({w for w, _ in win_scores})
        diffs = [st.mean(win_scores[(w, "V4")]) - st.mean(win_scores[(w, "V2")])
                 for w in windows if win_scores.get((w, "V4")) and win_scores.get((w, "V2"))]
        out["criteria"][crit] = {
            "label": label,
            **{var: {"n_participants": len(xs), "mean": round(ci95(xs)[0], 2), "ci95_halfwidth": round(ci95(xs)[1], 2)}
               for var, xs in per_var_part.items() if xs},
            "wilcoxon_V4_minus_V2": {**wilcoxon_exact(diffs), "n_windows": len(diffs),
                                     "mean_diff": round(st.mean(diffs), 3) if diffs else None},
        }

    (resp_path.with_name("mos_summary.json")).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# MOS — V2 so với V4", "", f"Người nghe hợp lệ: {out['n_participants']}; bị loại: {len(excluded)} {excluded or ''}", "",
          "| Tiêu chí | V2: MOS ± KTC95% | V4: MOS ± KTC95% | Δ TB (V4−V2) theo đoạn | Wilcoxon p (n đoạn) |", "|---|---|---|---|---|"]
    for crit, label in CRITERIA:
        c = out["criteria"][crit]

        def f(v: str) -> str:
            return f"{c[v]['mean']} ± {c[v]['ci95_halfwidth']}" if v in c else "–"
        w = c["wilcoxon_V4_minus_V2"]
        p = "–" if w["p"] is None else ("<0,0001" if w["p"] < 0.0001 else f"{w['p']:.4f}")
        md.append(f"| {label} | {f('V2')} | {f('V4')} | {w['mean_diff']} | {p} ({w['n_windows']}) |")
    resp_path.with_name("mos_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
