"""Trích số liệu từ log của AI worker (chỉ đọc log, không gọi API) — bản cập nhật 22/11/2026.

Đọc được:
  1. Dòng TIMING theo chunk và theo job (nguồn số liệu Bảng 4, xem NCKH/CAP_NHAT_SAU_TOI_UU_DUBBING.md mục 6.1):
       TIMING job=46 chunk=1 cau=29 asr=0.0s dich=3.7s cho_chunk_truoc=200.4s tts=8.4s ghep=0.4s nhac=1.7s upload=9.5s tong=224.1s
       TIMING job=46 final=5.0s (2 chunk)
     Thời gian xử lý thật của chunk = tong − cho_chunk_truoc. asr=0 nghĩa là dùng lại bản ký âm (KHÔNG phải lần đầu).
  2. Mốc thời gian (cần `docker logs --timestamps`): bắt đầu job ("Bat dau pipeline long tieng: job=N"),
     báo xong chunk k (PUT .../jobs/N/chunks/k), báo xong job (POST .../jobs/N/finish), task succeeded.
     -> thời gian tới đoạn đầu, tới khi người dùng thấy xong, tổng thời gian task.
  3. Tăng tốc cả đoạn / cắt đuôi (RE_TEMPO, RE_CUT — chỉ ghi khi có tăng tốc hoặc trễ > 2 s).
  4. Câu còn R > 1,3 sau bước rút gọn (RE_CAP). LƯU Ý: từ 15/11 cảnh báo này ghi cho MỌI câu còn R > 1,3 khi
     tăng tốc, KỂ CẢ câu khung < 2 s không được rút gọn. Muốn tách 2 loại thì kết hợp `transcript_segments.was_summarized`.
  5. Nhạc nền (BGM ...), lỗi hết credit (402), key không hợp lệ (401), upload chậm.

Dùng:
    docker logs --timestamps --since 2026-11-23T00:00:00Z lms_ai_worker 2>&1 | \
        python3 -I NCKH/experiments/parse_worker_logs.py --jobs 50,51 --out NCKH/experiments/results/server_<ngày>/worker_logs.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime

RE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)Z?\s")
RE_TIMING_CHUNK = re.compile(
    r"TIMING job=(\d+) chunk=(\d+) cau=(\d+) asr=([\d.]+)s dich=([\d.]+)s(?: cho_chunk_truoc=([\d.]+)s)? "
    r"tts=([\d.]+)s ghep=([\d.]+)s(?: nhac=([\d.]+)s)?(?: upload=([\d.]+)s)?(?: tong=([\d.]+)s)?")
RE_TIMING_FINAL = re.compile(r"TIMING job=(\d+) final=([\d.]+)s \((\d+) chunk\)")
RE_START = re.compile(r"Bat dau pipeline long tieng: job=(\d+)")
RE_CHUNK_PUT = re.compile(r"jobs/(\d+)/chunks/(\d+)\S*\s.*?\b(2\d\d)\b")
RE_FINISH = re.compile(r"jobs/(\d+)/finish\S*\s.*?\b(2\d\d)\b")
RE_SUCCEEDED = re.compile(r"run_pipeline\[[^\]]+\] succeeded in ([\d.]+)s.*?'jobId': (\d+)")
RE_TEMPO = re.compile(r"Chunk (\d+) job (\d+): tre toi da ([\d.]+)s, dai tho ([\d.]+)s -> tang toc ca doan x([\d.]+)")
RE_CUT = re.compile(r"Chunk (\d+) job (\d+): van du ([\d.]+)s sau khi tang toc toi da x([\d.]+)")
RE_CAP = re.compile(r"Segment seq=(\d+) van R=([\d.]+) > 1\.3")          # bỏ "sau N lan rut gon" (đã đổi 15/11)
RE_CREDIT = re.compile(r"HET CREDIT \(402\)")
RE_KEY = re.compile(r"API key not valid|401")
RE_BGM = re.compile(r"\bBGM\b(.*)")


def _ts(line: str) -> datetime | None:
    m = RE_TS.match(line)
    if not m:
        return None
    raw = m.group(1)
    if "." in raw:
        head, frac = raw.split(".")
        raw = f"{head}.{frac[:6]}"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", default="", help="Chỉ lấy các job id này (phân cách dấu phẩy)")
    ap.add_argument("--out", default="", help="Ghi thêm JSON vào đường dẫn này")
    args = ap.parse_args()
    only = {x.strip() for x in args.jobs.split(",") if x.strip()}
    want = (lambda j: not only or j in only)

    timing: dict[str, list[dict]] = defaultdict(list)
    final: dict[str, dict] = {}
    start: dict[str, datetime] = {}
    chunk_done: dict[str, dict[int, datetime]] = defaultdict(dict)
    finish: dict[str, datetime] = {}
    succeeded: dict[str, float] = {}
    tempo: dict[str, list[dict]] = defaultdict(list)
    cut: dict[str, list[dict]] = defaultdict(list)
    caps: list[dict] = []
    credit = key_err = 0
    bgm: list[str] = []
    has_ts = False

    for line in sys.stdin:
        ts = _ts(line)
        has_ts = has_ts or ts is not None
        if (m := RE_TIMING_CHUNK.search(line)) and want(m.group(1)):
            g = m.groups()
            f = lambda x: float(x) if x is not None else None  # noqa: E731
            row = {"chunk": int(g[1]), "cau": int(g[2]), "asr": f(g[3]), "dich": f(g[4]), "cho_chunk_truoc": f(g[5]) or 0.0,
                   "tts": f(g[6]), "ghep": f(g[7]), "nhac": f(g[8]), "upload": f(g[9]), "tong": f(g[10])}
            row["xu_ly_that"] = round(row["tong"] - row["cho_chunk_truoc"], 2) if row["tong"] is not None else None
            timing[g[0]].append(row)
            continue
        if (m := RE_TIMING_FINAL.search(line)) and want(m.group(1)):
            final[m.group(1)] = {"final_s": float(m.group(2)), "n_chunks": int(m.group(3))}
            continue
        if (m := RE_START.search(line)) and want(m.group(1)) and ts:
            start.setdefault(m.group(1), ts)
            continue
        if (m := RE_FINISH.search(line)) and want(m.group(1)) and ts:
            finish[m.group(1)] = ts
            continue
        if (m := RE_CHUNK_PUT.search(line)) and want(m.group(1)) and ts:
            chunk_done[m.group(1)].setdefault(int(m.group(2)), ts)
            continue
        if (m := RE_SUCCEEDED.search(line)) and want(m.group(2)):
            succeeded[m.group(2)] = float(m.group(1))
            continue
        if (m := RE_TEMPO.search(line)) and want(m.group(2)):
            tempo[m.group(2)].append({"chunk": int(m.group(1)), "max_delay_s": float(m.group(3)),
                                      "raw_length_s": float(m.group(4)), "tempo": float(m.group(5))})
            continue
        if (m := RE_CUT.search(line)) and want(m.group(2)):
            cut[m.group(2)].append({"chunk": int(m.group(1)), "excess_s": float(m.group(3)), "max_tempo": float(m.group(4))})
            continue
        if m := RE_CAP.search(line):
            caps.append({"seq": int(m.group(1)), "R": float(m.group(2))})
        if RE_CREDIT.search(line):
            credit += 1
        if "gemini" in line.lower() and RE_KEY.search(line):
            key_err += 1
        if m := RE_BGM.search(line):
            bgm.append(m.group(0).strip()[:200])

    jobs = sorted(set(timing) | set(final) | set(start) | set(succeeded) | set(tempo) | set(cut), key=int)
    out: dict = {"jobs": {}, "capped_warnings": len(caps), "capped_detail": caps,
                 "het_credit_lines": credit, "gemini_key_error_lines": key_err, "bgm_lines": bgm,
                 "had_timestamps": has_ts,
                 "notes": ["capped_warnings gồm cả câu khung < 2 s không được rút gọn; tách bằng was_summarized.",
                           "asr=0 ở chunk nghĩa là dùng lại bản ký âm — không phải lần lồng tiếng đầu.",
                           "upload lớn bất thường (> 30 s) nên ghi chú/chạy lại, không lấy trung bình lẫn vào."]}
    for j in jobs:
        rows = sorted(timing.get(j, []), key=lambda r: r["chunk"])
        t0 = start.get(j)
        cd = chunk_done.get(j, {})
        info = {
            "chunks_timing": rows,
            "final": final.get(j),
            "task_succeeded_s": succeeded.get(j),
            "first_chunk_s": round((cd[min(cd)] - t0).total_seconds(), 1) if t0 and cd else None,
            "chunk_done_s": {k: round((v - t0).total_seconds(), 1) for k, v in sorted(cd.items())} if t0 else {},
            "user_sees_done_s": round((finish[j] - t0).total_seconds(), 1) if t0 and j in finish else None,
            "sum_xu_ly_that_s": round(sum(r["xu_ly_that"] or 0 for r in rows), 1) if rows else None,
            "asr_reused": any((r["asr"] or 0) == 0 for r in rows) if rows else None,
            "max_upload_s": max((r["upload"] or 0 for r in rows), default=None),
            "chunks_logged_tempo": tempo.get(j, []), "chunks_cut_tail": cut.get(j, []),
        }
        out["jobs"][j] = info

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1, default=str)

    if not has_ts:
        print("> Cảnh báo: log không có mốc thời gian — chạy `docker logs --timestamps` để tính thời gian tới đoạn đầu.\n")
    print("| Job | Chunk | Câu | ASR dùng lại | Tới đoạn đầu (s) | Người dùng thấy xong (s) | Task (s) | Σ xử lý thật (s) | Upload max (s) | Tempo max | Cắt đuôi |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for j, i in out["jobs"].items():
        rows = i["chunks_timing"]
        print(f"| {j} | {len(rows) or (i['final'] or {}).get('n_chunks', '–')} | {sum(r['cau'] for r in rows) if rows else '–'} | "
              f"{i['asr_reused']} | {i['first_chunk_s']} | {i['user_sees_done_s']} | {i['task_succeeded_s']} | "
              f"{i['sum_xu_ly_that_s']} | {i['max_upload_s']} | "
              f"{max((x['tempo'] for x in i['chunks_logged_tempo']), default='–')} | {len(i['chunks_cut_tail'])} |")
    print("\nChi tiết TIMING từng chunk:")
    print("| Job | Chunk | asr | dịch | chờ chunk trước | tts | ghép | nhạc | upload | tổng | xử lý thật |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for j, i in out["jobs"].items():
        for r in i["chunks_timing"]:
            print(f"| {j} | {r['chunk']} | {r['asr']} | {r['dich']} | {r['cho_chunk_truoc']} | {r['tts']} | {r['ghep']} | "
                  f"{r['nhac']} | {r['upload']} | {r['tong']} | {r['xu_ly_that']} |")
    print(f"\nCâu còn R > 1,3 khi tăng tốc (gồm cả câu ngắn không rút gọn): {len(caps)}; "
          f"'HET CREDIT (402)': {credit}; lỗi key Gemini: {key_err}; dòng BGM: {len(bgm)}")


if __name__ == "__main__":
    main()
