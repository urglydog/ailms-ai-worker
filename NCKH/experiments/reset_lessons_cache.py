"""Dọn phần dữ liệu NGOÀI MySQL mà hệ thống dùng lại, để đo "lần lồng tiếng đầu" (mục 6.3 của
NCKH/CAP_NHAT_SAU_TOI_UU_DUBBING.md). Phần MySQL xóa bằng `reset_lessons.sql`.

Mặc định chỉ LIỆT KÊ (dry-run). Thêm --apply để xóa thật.
  - B2: các object dưới `bgm/{lesson_id}/` (nhạc nền đã tách).
  - Redis: `dubbing:tts_cps:{voice}` (tốc độ đọc của giọng) — chỉ khi có --reset-cps.
  - Redis: `courseDetails::*` (cache trang khóa học) — chỉ khi có --course-cache.

Chạy trong container ai-worker:
    docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/reset_lessons_cache.py \
        --lessons 2284,2285,2286,2288 --reset-cps --voices vi-VN-HoaiMyNeural,vi-VN-NamMinhNeural
    (... rồi chạy lại với --apply sau khi xem danh sách)
In ra giá trị tts_cps TRƯỚC khi xóa để chép vào NOTES. Không in key/token.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import redis_client  # noqa: E402
from app.config import settings  # noqa: E402
from app.storage import _get_client  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lessons", required=True, help="lesson id, phân cách dấu phẩy")
    ap.add_argument("--voices", default="vi-VN-HoaiMyNeural,vi-VN-NamMinhNeural")
    ap.add_argument("--reset-cps", action="store_true", help="xóa tốc độ đọc đã đo của các giọng")
    ap.add_argument("--course-cache", action="store_true", help="xóa cache Redis courseDetails::*")
    ap.add_argument("--apply", action="store_true", help="xóa thật (mặc định chỉ liệt kê)")
    args = ap.parse_args()
    lessons = [x.strip() for x in args.lessons.split(",") if x.strip()]
    mode = "XÓA" if args.apply else "DRY-RUN (chỉ liệt kê)"
    print(f"== {mode}")

    s3 = _get_client()
    bucket = settings.b2_bucket_name
    for lid in lessons:
        keys = []
        token = None
        while True:
            kw = {"Bucket": bucket, "Prefix": f"bgm/{lid}/"}
            if token:
                kw["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kw)
            keys += [o["Key"] for o in resp.get("Contents", [])]
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        print(f"B2 bgm/{lid}/: {len(keys)} object" + (f" (vd {keys[:2]})" if keys else ""))
        if args.apply:
            for k in keys:
                s3.delete_object(Bucket=bucket, Key=k)

    r = redis_client.get_client()
    for v in [x.strip() for x in args.voices.split(",") if x.strip()]:
        key = f"dubbing:tts_cps:{v}"
        print(f"Redis {key} = {r.get(key)}")
        if args.reset_cps and args.apply:
            r.delete(key)
    if args.course_cache:
        ks = list(r.scan_iter("courseDetails::*"))
        print(f"Redis courseDetails::*: {len(ks)} khóa")
        if args.apply and ks:
            r.delete(*ks)
    print("Xong." if args.apply else "Chưa xóa gì. Chạy lại với --apply để xóa.")


if __name__ == "__main__":
    main()
