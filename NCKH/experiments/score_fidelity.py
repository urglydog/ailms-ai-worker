"""Tổng hợp điểm chấm độ trung thành (L4) của 2 người: % mỗi mức, độ đồng thuận, hệ số kappa của Cohen.

Thang điểm: 2 = giữ đủ ý, 1 = mất ý phụ, 0 = mất/sai ý chính.
Dùng:
    python NCKH/experiments/score_fidelity.py NCKH/experiments/results/full_r1 --suffix _v2
Đọc  <run_dir>/fidelity_scores<suffix>.csv  (cột: id, score_rater1, score_rater2; ô trống = chưa chấm, bị bỏ qua)
Ghi  <run_dir>/fidelity_summary<suffix>.md / .json
Chỉ dùng thư viện chuẩn. Nếu có người chấm trả lời toàn một mức thì kappa không xác định (None) — báo rõ trong kết quả.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

LEVELS = (2, 1, 0)


def parse(x: str) -> int | None:
    x = (x or "").strip()
    if x == "":
        return None
    v = int(x)
    if v not in LEVELS:
        raise ValueError(f"Điểm không hợp lệ: {x!r} (chỉ 0, 1, 2)")
    return v


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in LEVELS)
    if pe >= 1.0:
        return None
    return (po - pe) / (1 - pe)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    with (run_dir / f"fidelity_scores{args.suffix}.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    r1, r2, both1, both2, ids_skipped = [], [], [], [], []
    for r in rows:
        a, b = parse(r["score_rater1"]), parse(r["score_rater2"])
        if a is not None:
            r1.append(a)
        if b is not None:
            r2.append(b)
        if a is None or b is None:
            ids_skipped.append(r["id"])
        else:
            both1.append(a)
            both2.append(b)

    def dist(xs: list[int]) -> dict:
        n = len(xs)
        return {str(l): {"n": xs.count(l), "pct": round(100.0 * xs.count(l) / n, 1) if n else 0.0} for l in LEVELS}

    n = len(both1)
    agree = round(100.0 * sum(1 for x, y in zip(both1, both2) if x == y) / n, 1) if n else None
    kappa = cohen_kappa(both1, both2)
    out = {
        "n_items": len(rows), "n_rater1": len(r1), "n_rater2": len(r2), "n_both": n,
        "rater1": dist(r1), "rater2": dist(r2),
        "exact_agreement_pct": agree,
        "cohen_kappa": round(kappa, 3) if kappa is not None else None,
        "kappa_note": "không xác định (một người chấm toàn một mức)" if kappa is None and n else "",
        "items_missing_a_score": ids_skipped,
    }
    (run_dir / f"fidelity_summary{args.suffix}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Độ trung thành câu rút gọn (L4) — `{run_dir.name}`", "",
          f"Số câu: {out['n_items']}; người 1 chấm {out['n_rater1']}, người 2 chấm {out['n_rater2']}, cả hai chấm {n}.", "",
          "| Mức | Người 1 (n, %) | Người 2 (n, %) |", "|---|---|---|"]
    names = {2: "2 — giữ đủ ý", 1: "1 — mất ý phụ", 0: "0 — mất/sai ý chính"}
    for l in LEVELS:
        md.append(f"| {names[l]} | {out['rater1'][str(l)]['n']} ({out['rater1'][str(l)]['pct']}%) | "
                  f"{out['rater2'][str(l)]['n']} ({out['rater2'][str(l)]['pct']}%) |")
    md += ["", f"Tỷ lệ trùng khớp tuyệt đối: {agree}%", f"Hệ số kappa của Cohen: {out['cohen_kappa']} {out['kappa_note']}"]
    (run_dir / f"fidelity_summary{args.suffix}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
