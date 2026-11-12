"""Trích số liệu ghép audio từ log của AI worker (chỉ đọc log, không gọi API).

Pipeline sau bản sửa 11/11/2026 chỉ GHI LOG khi đoạn phải tăng tốc hoặc có câu trễ > 2 s, hoặc khi vẫn dư sau
khi tăng tốc tối đa (phần cuối bị cắt). Không có dòng log nghĩa là đoạn đó khớp sẵn — không phải thiếu dữ liệu.
Cũng đếm cảnh báo câu chạm trần (+30%) và lỗi hết credit.

Dùng:
    docker logs --since 2026-11-12T00:00:00Z lms_ai_worker 2>&1 | python3 -I NCKH/experiments/parse_worker_logs.py [--jobs 21,22]
Ghi ra stdout bảng markdown (chép vào REPORT) và JSON cạnh đó nếu có --out.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict

RE_TEMPO = re.compile(r"Chunk (\d+) job (\d+): tre toi da ([\d.]+)s, dai tho ([\d.]+)s -> tang toc ca doan x([\d.]+)")
RE_CUT = re.compile(r"Chunk (\d+) job (\d+): van du ([\d.]+)s sau khi tang toc toi da x([\d.]+)")
RE_CAP = re.compile(r"Segment seq=(\d+) van R=([\d.]+) > 1\.3 sau (\d+) lan rut gon")
RE_CREDIT = re.compile(r"HET CREDIT \(402\)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", default="", help="Chỉ lấy các job id này (phân cách dấu phẩy)")
    ap.add_argument("--out", default="", help="Ghi thêm JSON vào đường dẫn này")
    args = ap.parse_args()
    only = {x.strip() for x in args.jobs.split(",") if x.strip()}

    tempo: dict[str, list[dict]] = defaultdict(list)
    cut: dict[str, list[dict]] = defaultdict(list)
    caps = credit = 0
    for line in sys.stdin:
        m = RE_TEMPO.search(line)
        if m and (not only or m.group(2) in only):
            tempo[m.group(2)].append({"chunk": int(m.group(1)), "max_delay_s": float(m.group(3)),
                                      "raw_length_s": float(m.group(4)), "tempo": float(m.group(5))})
            continue
        m = RE_CUT.search(line)
        if m and (not only or m.group(2) in only):
            cut[m.group(2)].append({"chunk": int(m.group(1)), "excess_s": float(m.group(3)), "max_tempo": float(m.group(4))})
            continue
        if RE_CAP.search(line):
            caps += 1
        if RE_CREDIT.search(line):
            credit += 1

    jobs = sorted(set(tempo) | set(cut), key=int)
    res = {"jobs": {j: {"chunks_logged_tempo": tempo.get(j, []), "chunks_cut_tail": cut.get(j, [])} for j in jobs},
           "capped_warnings_total": caps, "het_credit_lines": credit,
           "note": "Chỉ đoạn có tăng tốc / trễ > 2 s / bị cắt mới có dòng log; vắng dòng = khớp sẵn."}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    print("| Job | Đoạn có ghi log tăng tốc | Tempo max | Trễ lớn nhất trước tăng tốc (s) | Đoạn bị cắt đuôi | Cắt tối đa (s) |")
    print("|---|---|---|---|---|---|")
    for j in jobs:
        t, c = tempo.get(j, []), cut.get(j, [])
        print(f"| {j} | {len(t)} | {max((x['tempo'] for x in t), default='–')} | "
              f"{max((x['max_delay_s'] for x in t), default='–')} | {len(c)} | {max((x['excess_s'] for x in c), default='–')} |")
    print(f"\nCảnh báo câu chạm trần (+30%): {caps}; dòng 'HET CREDIT (402)': {credit}")


if __name__ == "__main__":
    main()
