"""Tổng hợp số liệu server (S1–S3) từ file TSV do server_job_stats_ext.sql xuất ra. Chỉ dùng thư viện chuẩn.

Dùng:
    python3 NCKH/experiments/analyze_server.py NCKH/experiments/results/server_YYYYMMDD/out.tsv [--exclude-jobs 12,13]
Ghi <thư mục của out.tsv>/server_summary.md và server_summary.json.

--exclude-jobs: ID job test/lỗi cần loại (Thiện tự xác định, ghi lý do trong REPORT). Job bị loại vẫn được đếm riêng.
speech_rate: phân loại theo 3 vùng của thuật toán — "=1,0" (đọc tốc độ mặc định/đệm lặng), "1,0–1,3" (tăng tốc), "=1,3" (chạm trần +30%).
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def parse_sections(path: Path) -> dict[str, list[dict]]:
    sections: dict[str, list[dict]] = {}
    cur: str | None = None
    header: list[str] | None = None
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if not row:
                continue
            if row[0].startswith("##"):
                cur, header = row[0][2:], None
                sections[cur] = []
                continue
            if cur is None:
                continue
            if header is None:
                header = row          # dòng đầu sau marker là tên cột
                continue
            if row == ["section"]:
                continue
            sections[cur].append(dict(zip(header, row)))
    sections.pop("section", None)
    return sections


def num(x: str) -> float | None:
    x = (x or "").strip()
    return None if x in ("", "NULL") else float(x)


def stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(st.mean(xs), 2), "median": round(st.median(xs), 2),
            "min": round(min(xs), 2), "max": round(max(xs), 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tsv")
    ap.add_argument("--exclude-jobs", default="")
    args = ap.parse_args()
    path = Path(args.tsv)
    excl = {x.strip() for x in args.exclude_jobs.split(",") if x.strip()}
    sec = parse_sections(path)

    jobs_all = sec.get("JOBS", [])
    jobs = [j for j in jobs_all if j["job_id"] not in excl]
    out: dict = {"n_jobs_total": len(jobs_all), "n_jobs_excluded": len(jobs_all) - len(jobs),
                 "excluded_job_ids": sorted(excl)}

    # --- S1: job ---
    out["status"] = dict(Counter(j["status"] for j in jobs))
    out["retry_count"] = stats([num(j["retry_count"]) or 0.0 for j in jobs])
    done = [j for j in jobs if j["status"] == "COMPLETED"]
    per_min = []
    for j in done:
        p, d = num(j["processing_sec"]), num(j["lesson_duration_sec"])
        if p is not None and d and d > 0:
            per_min.append(p / (d / 60.0))
    out["processing_sec_per_video_min"] = stats(per_min)
    out["first_chunk_sec"] = stats([x for x in (num(j["first_chunk_sec"]) for j in done) if x is not None])
    out["queue_wait_sec"] = stats([x for x in (num(j["queue_wait_sec"]) for j in jobs) if x is not None])
    out["per_job"] = [{
        "job_id": j["job_id"], "lesson_id": j["lesson_id"], "status": j["status"],
        "lesson_duration_sec": num(j["lesson_duration_sec"]), "processing_sec": num(j["processing_sec"]),
        "first_chunk_sec": num(j["first_chunk_sec"]), "queue_wait_sec": num(j["queue_wait_sec"]),
        "retry_count": num(j["retry_count"]), "total_chunks": num(j["total_chunks"]),
        "processing_sec_per_video_min": round(num(j["processing_sec"]) / (num(j["lesson_duration_sec"]) / 60.0), 2)
        if num(j["processing_sec"]) is not None and num(j["lesson_duration_sec"]) else None,
    } for j in jobs]

    # --- thời gian từng đoạn: khoảng cách giữa các lần hoàn tất đoạn ---
    chunk_gaps: list[float] = []
    by_track: dict[tuple, list[dict]] = defaultdict(list)
    for c in sec.get("AUDIO_CHUNKS", []):
        by_track[(c["lesson_id"], c["language"])].append(c)
    for rows in by_track.values():
        ts = [datetime.fromisoformat(r["created_at"]) for r in sorted(rows, key=lambda r: int(r["chunk_index"]))]
        chunk_gaps += [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    out["seconds_between_chunk_completions"] = stats(chunk_gaps)

    # --- S2: tốc độ đọc và tỷ lệ rút gọn ---
    segs = sec.get("SEGMENTS", [])
    rates = [num(s["speech_rate"]) for s in segs if num(s["speech_rate"]) is not None]
    n = len(rates)

    def zone(r: float) -> str:
        if r <= 1.005:
            return "=1,0"
        if r >= 1.295:
            return "=1,3 (chạm trần)"
        return "1,0–1,3"
    zc = Counter(zone(r) for r in rates)
    out["segments"] = {
        "n": len(segs),
        "speech_rate_zones_pct": {k: round(100.0 * v / n, 1) for k, v in zc.items()} if n else {},
        "pct_was_summarized": round(100.0 * sum(1 for s in segs if s["was_summarized"] in ("1", "true", "True")) / len(segs), 1)
        if segs else None,
        "pct_frame_lt_2s": round(100.0 * sum(1 for s in segs if (num(s["t_orig"]) or 0) < 2.0) / len(segs), 1) if segs else None,
    }

    # --- S3: tái sử dụng + độ dài audio so với bài ---
    tracks = sec.get("TRACKS", [])
    out["tracks"] = [{
        "lesson_id": t["lesson_id"], "language": t["language"], "status": t["status"],
        "track_duration_sec": num(t["track_duration_sec"]), "lesson_duration_sec": num(t["lesson_duration_sec"]),
        "diff_sec": num(t["diff_sec"]), "play_count": num(t["play_count"]),
    } for t in tracks]
    diffs = [abs(num(t["diff_sec"])) for t in tracks if num(t["diff_sec"]) is not None]
    out["abs_duration_diff_sec"] = stats(diffs)
    out["lessons_with_2plus_languages"] = sum(1 for k, v in Counter(t["lesson_id"] for t in tracks).items() if v >= 2)
    out["total_play_count"] = sum(num(t["play_count"]) or 0 for t in tracks)

    path.with_name("server_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Số liệu server (S1–S3) — `{path.parent.name}`", "",
          f"Job: {out['n_jobs_total']} (loại {out['n_jobs_excluded']}: {', '.join(sorted(excl)) or 'không'}). Trạng thái: {out['status']}", "",
          "| Chỉ số | n | TB | Trung vị | Min | Max |", "|---|---|---|---|---|---|"]
    for label, key in [("Giây xử lý / phút video (job COMPLETED)", "processing_sec_per_video_min"),
                       ("Giây tới đoạn đầu tiên", "first_chunk_sec"), ("Giây chờ hàng đợi", "queue_wait_sec"),
                       ("Số lần thử lại", "retry_count"), ("Giây giữa 2 đoạn hoàn tất", "seconds_between_chunk_completions"),
                       ("|Chênh thời lượng audio − bài| (giây)", "abs_duration_diff_sec")]:
        s = out[key]
        md.append(f"| {label} | {s.get('n', 0)} | {s.get('mean', '–')} | {s.get('median', '–')} | {s.get('min', '–')} | {s.get('max', '–')} |")
    md += ["", f"Câu: {out['segments']['n']}; tốc độ đọc: {out['segments']['speech_rate_zones_pct']}; "
               f"% câu bị rút gọn: {out['segments']['pct_was_summarized']}; % câu có khung < 2 s: {out['segments']['pct_frame_lt_2s']}",
           f"Tái sử dụng: {out['lessons_with_2plus_languages']} bài có ≥ 2 ngôn ngữ; tổng lượt phát: {out['total_play_count']}"]
    path.with_name("server_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
