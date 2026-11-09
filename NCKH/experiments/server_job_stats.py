"""Xuất số liệu lồng tiếng từ MySQL của server ra CSV — CHỈ ĐỌC.

An toàn:
  - Phiên kết nối đặt `SET SESSION TRANSACTION READ ONLY`, script chỉ chạy các câu
    SELECT trong server_job_stats.sql (câu nào không bắt đầu bằng SELECT sẽ bị từ chối).
  - Không tạo job, không gọi API của backend.
  - Thông tin kết nối đọc từ biến môi trường, KHÔNG ghi vào file/commit.

Kết nối (chọn 1):
  a) Qua SSH tunnel (khuyên dùng, không mở cổng MySQL ra ngoài):
        ssh -N -L 3307:127.0.0.1:3306 <user>@<server>
     rồi đặt NCKH_DB_HOST=127.0.0.1, NCKH_DB_PORT=3307
     (nếu MySQL chạy trong Docker không publish cổng, thay 127.0.0.1:3306 bằng IP container)
  b) Chạy thẳng trên server: copy file .sql lên rồi dùng `docker exec -i <mysql> mysql ...`

Biến môi trường:
  NCKH_DB_HOST, NCKH_DB_PORT (3306), NCKH_DB_USER, NCKH_DB_PASSWORD, NCKH_DB_NAME

Cài thư viện (chỉ cho script này):  pip install pymysql
Chạy:  python NCKH/experiments/server_job_stats.py
Đầu ra: NCKH/experiments/results/server_<ngày>/{jobs,segments,reuse}.csv + summary in ra màn hình
"""

from __future__ import annotations

import csv
import os
import re
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
SQL_FILE = HERE / "server_job_stats.sql"
NAMES = ["jobs", "segments", "reuse"]


def load_queries() -> list[str]:
    text = re.sub(r"--[^\n]*", "", SQL_FILE.read_text(encoding="utf-8"))
    stmts = [s.strip() for s in text.split(";") if s.strip()]
    selects = [s for s in stmts if not s.upper().startswith("SET ")]
    for s in selects:
        if not s.upper().startswith("SELECT"):
            sys.exit(f"Từ chối chạy câu lệnh không phải SELECT:\n{s[:200]}")
    return selects


def main() -> None:
    try:
        import pymysql
    except ImportError:
        sys.exit("Thiếu pymysql: pip install pymysql")

    need = ["NCKH_DB_HOST", "NCKH_DB_USER", "NCKH_DB_PASSWORD", "NCKH_DB_NAME"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        sys.exit(f"Thiếu biến môi trường: {', '.join(miss)}")

    conn = pymysql.connect(
        host=os.environ["NCKH_DB_HOST"], port=int(os.environ.get("NCKH_DB_PORT", "3306")),
        user=os.environ["NCKH_DB_USER"], password=os.environ["NCKH_DB_PASSWORD"],
        database=os.environ["NCKH_DB_NAME"], charset="utf8mb4", connect_timeout=15,
        cursorclass=pymysql.cursors.DictCursor,
    )
    out = HERE / "results" / f"server_{datetime.now():%Y%m%d_%H%M}"
    out.mkdir(parents=True, exist_ok=True)
    data: dict[str, list[dict]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            for name, q in zip(NAMES, load_queries()):
                cur.execute(q)
                rows = cur.fetchall()
                data[name] = rows
                if rows:
                    with (out / f"{name}.csv").open("w", newline="", encoding="utf-8-sig") as f:
                        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                        w.writeheader()
                        w.writerows(rows)
                print(f"{name}: {len(rows)} dòng")
    finally:
        conn.close()

    # Tóm tắt nhanh
    jobs = [j for j in data.get("jobs", []) if j["status"] == "COMPLETED" and j["processing_sec"] is not None]
    if jobs:
        spm = [j["processing_sec"] / (j["lesson_duration_sec"] / 60) for j in jobs if j["lesson_duration_sec"]]
        first = [j["first_chunk_sec"] for j in jobs if j["first_chunk_sec"] is not None]
        print(f"\nJob hoàn thành: {len(jobs)} / {len(data['jobs'])}")
        if spm:
            print(f"Thời gian xử lý / phút video: TB {st.mean(spm):.1f}s, trung vị {st.median(spm):.1f}s")
        if first:
            print(f"Thời gian ra đoạn đầu tiên: TB {st.mean(first):.0f}s, trung vị {st.median(first):.0f}s")
    segs = data.get("segments", [])
    if segs:
        rates = [float(s["speech_rate"]) for s in segs if s["speech_rate"] is not None]
        summ = sum(1 for s in segs if s["was_summarized"])
        print(f"Câu đã lồng tiếng: {len(segs)}; bị rút gọn: {100 * summ / len(segs):.1f}%")
        if rates:
            print(f"Hệ số tốc độ: TB {st.mean(rates):.3f}; >1.0: {100 * sum(r > 1.0 for r in rates) / len(rates):.1f}%; "
                  f"=1.3: {100 * sum(r >= 1.299 for r in rates) / len(rates):.1f}%")
    print(f"\nĐã lưu: {out}")


if __name__ == "__main__":
    main()
