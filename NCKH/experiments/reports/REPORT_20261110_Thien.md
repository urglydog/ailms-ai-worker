# REPORT đo đạc – 10/11/2026 – Thiện (thực hiện cùng Claude Code)

> **Trạng thái: CHƯA HOÀN TẤT.** Đã xong L1 (một phần), L2, L4 (chuẩn bị mẫu), L6. **L3 THẤT BẠI do hết credit Gemini**
> (lỗi 402 "prepayment credits are depleted", mục 3 và 5.9): `full_r2` chỉ có `lec01`, `full_r3` không có dữ liệu.
> Chưa làm: S1–S5 (cần Sang), L5 (MOS), chấm L4 (cần người). **Cần nạp credit Gemini trước khi chạy tiếp bất cứ thứ gì gọi LLM.**
> Mọi con số dưới đây truy được về file trong `NCKH/experiments/results/` (ghi ở từng mục).

## 0. Tóm tắt nhanh

- **Đã làm:** L1 (nguồn + link; giấy phép chưa xác minh), L2 (`full_r1`: 4 bài, 50 phút, 787 câu, V1–V4, chạy hết độ dài),
  kiểm tra ghép audio thật (V2, V4), ước lượng độ trễ cộng dồn, lấy mẫu L4, L6 (cấu hình máy).
- **Thất bại:** L3 (`full_r2`, `full_r3`, V2 và V4): Gemini trả lỗi 402, credit prepay đã hết. Dữ liệu dở dang vẫn được giữ lại (mục 3).
- **Chưa làm:** S1–S5 (server), L5 (MOS), chấm L4, đo qua chức năng lồng tiếng thật trên web — lý do ở mục 3.
- **Cảnh báo vận hành:** key Gemini trong container `lms_ai_worker` (container chạy cả hệ thống thật) đang hết credit; các tính năng AI dùng
  key này có thể đang lỗi (chưa kiểm tra tác động thật) — mục 5.9.
- **Số chính** (n=787 câu, `results/full_r1/summary.md`): Δ trung bình V1 → V4 = 1,649 → 0,190 s; % câu còn tràn 94,0 → 26,7;
  số lần gọi LLM 7 → 690.
- **Phát hiện cần nhóm xem lại (quan trọng):** ghép lại audio thật cho thấy audio lồng tiếng **dài hơn bản gốc** và các câu
  **trễ dần** so với video: V4 dài hơn +1,7% đến +10,7% (+9,4 s đến +95,9 s tuỳ bài), V2 dài hơn +18% đến +34% (mục 4.3).
  Điều này **không khớp** câu trong bài báo "âm thanh mỗi đoạn có thời lượng đúng bằng L, không tích lũy độ trễ" (mục 5).
- **Vấn đề dữ liệu:** cả 4 bài đều là CNTT, không có bài kỹ năng mềm; nhãn `category` trong manifest sai với nội dung.

## 1. Môi trường

| Mục | Local (đo ở đây) | Server vận hành |
|---|---|---|
| Commit ai-worker | `11378e5` (cây làm việc chỉ khác `videos.json` — trường `note` — và các script mới) | Chưa hỏi (S5) |
| Chạy ở đâu | Container `lms_ai_worker`, uid 1000:1001, trên host `ubuntu-4gb-fsn1-2` (**dùng chung với hệ thống đang chạy thật**) | Chưa đo |
| CPU / RAM / OS | 2 vCPU Intel Xeon Skylake / 3,7 GiB / Ubuntu 22.04.5, kernel 5.15.0-198 | Chưa đo |
| Mạng | Chưa đo | Chưa đo |
| GEMINI_MODEL / ASR / giọng | `gemini-3.5-flash` / `whisper-large-v3-turbo` / Azure Neural `vi-VN-HoaiMyNeural` và `vi-VN-NamMinhNeural` (theo `videos.json`) | Chưa xác nhận (S5) |
| CHUNK_MINUTES, MAX_RESUMMARIZE_ATTEMPTS | 10, 2 (từ `run_meta.json` và biến môi trường container) | Chưa xác nhận |
| Thời gian | `full_r1`: 10/11/2026 17:20:18 – 20:11:02 UTC | – |

Nguồn: `results/full_r1/run_meta.json`, `results/full_r1/NOTES.md`.

## 2. Dữ liệu

Đầu vào là **audio mp3** tách sẵn từ video (không phải file video). Nguồn do Thiện cung cấp; **giấy phép chưa xác minh**.

| id | Tên bài | Nguồn (URL) | Giấy phép | Nhãn trong manifest | Nội dung thực tế | Thời lượng | Số câu |
|---|---|---|---|---|---|---|---|
| lec01 | Crash Course CS #10: Early Programming | https://www.youtube.com/watch?v=nwDq4adJwzM | chưa xác minh | CNTT | CNTT | 566,0 s | 131 |
| lec02 | Crash Course CS #18: Operating Systems | https://www.youtube.com/watch?v=26QPDBe-NB8 | chưa xác minh | CNTT | CNTT | 815,1 s | 185 |
| lec03 | Crash Course CS #29: The Internet | https://www.youtube.com/watch?v=AEaKrq3SpW8 | chưa xác minh | **KyNangMem** | **CNTT** | 718,0 s | 181 |
| lec04 | Stanford CS229, Lecture 1 (15 phút đầu) | https://www.youtube.com/watch?v=UzxYlbK2c7E | chưa xác minh | **KyNangMem** | **CNTT** | 900,0 s | 290 |

Tổng 50,0 phút, 787 câu (`results/full_r1/videos.csv`). Ngôn ngữ nguồn ASR: English cho cả 4 bài.
Cách lấy dữ liệu: Thiện đã tách audio từ video YouTube ở đợt 1 (lệnh tách cụ thể chưa được ghi lại — **cần Thiện bổ sung**).

## 3. Các bước đã thực hiện

**L1 – Ghi nguồn dữ liệu** — *Một phần.*
- Mục đích: truy xuất nguồn bài giảng. Đã ghi link và thời lượng vào `note` trong `experiments/videos.json`.
- Còn thiếu: giấy phép, tên người giảng của từng bài; **không có bài kỹ năng mềm** (mục 5).

**L2 – Chạy toàn bộ độ dài** — *Xong.*
- Lệnh: `docker exec --user 1000:1001 lms_ai_worker python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r1 --keep-audio`
- Khác hướng dẫn: chạy bằng user thường (uid 1000) thay vì root để file kết quả không thuộc root.
- Đầu ra: `results/full_r1/` (`segments.csv`, `videos.csv`, `run_meta.json`, `summary.md/json`, `NOTES.md`, `audio/` không commit).
- Sự cố: không có lỗi. ASR gọi lại Groq cho `lec02`–`lec04` (`asr_cache=False`); `lec01` dùng cache đợt 1.
- Chạy `analyze.py` (bản đã sửa 10/11): `python NCKH/experiments/analyze.py NCKH/experiments/results/full_r1`.

**Kiểm tra ghép audio thật (bổ sung cho L2)** — *Xong cho V2 và V4.*
- Script mới `check_full_length.py` (do Claude viết, không sửa code app). Lệnh:
  `docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/check_full_length.py NCKH/experiments/results/full_r1 --variants V2,V4`
- Script ghép lại audio đúng cách `dubbing_service._process_chunk` (khoảng lặng = `start − prev_end` của bản gốc, đệm cuối đoạn nếu thiếu,
  nối đoạn bằng `audio_utils.concat_files`), rồi đo bằng `audio_utils.measure_duration_sec`. Không gọi API, không ghi DB.
- **Giới hạn:** đây là ghép lại từ file câu của thí nghiệm bằng đúng hàm của pipeline; chưa phải file `final.mp3` thật trên server.
- Không kiểm V3, vì nhánh `pad` của V3 không lưu file audio riêng. V1 không kiểm (không cần cho giả thuyết).

**Ước lượng độ trễ cộng dồn** — *Xong.* Script mới `drift_analysis.py`, đầu ra `results/full_r1/drift_summary.md/json`.

**L3 – Lặp lại** — *THẤT BẠI (hết credit Gemini).*
- Lệnh (chạy tuần tự): `docker exec --user 1000:1001 lms_ai_worker python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r2 --variants V2,V4 --keep-audio`, rồi tương tự với `--run-id full_r3`.
  Sau đó chuỗi lệnh chạy `analyze.py`, `drift_analysis.py` (và `aggregate_runs.py` ở cuối).
- `full_r2` (20:28:17 – 20:52:07 UTC): chỉ `lec01` xong (262 dòng = 131 câu × V2, V4). `lec02` lỗi `Max retries exceeded for Gemini API — tat ca slot deu that bai`;
  `lec03`, `lec04` lỗi `No active Gemini slot available (all in cooldown)`. Trong `results/full_r2/` chỉ có dữ liệu `lec01`; `summary.md` và `drift_summary.*`
  của run này **chỉ phản ánh `lec01`**, không dùng làm số liệu.
- `full_r3` (20:52:08 – 20:52:11): cả 4 bài lỗi ngay; không có `segments.csv`. Thư mục chỉ có `run_meta.json` và `audio/` rỗng.
- Chẩn đoán: mạng từ container tới Gemini/Groq/Google bình thường; một lần gọi thử Gemini (câu 1 từ, `maxOutputTokens=8`) trả `HTTP 402 RESOURCE_EXHAUSTED`:
  *"Your prepayment credits are depleted"*. Mã lỗi này không được provider phân biệt (log chỉ ghi "network error"/"cooldown"), nên log gốc dễ gây hiểu nhầm là lỗi mạng.
- **Không chạy lại** vì không có credit. Mục 4.1 chưa có trung bình ± độ lệch chuẩn. Cần nạp credit rồi chạy lại với run-id mới (ví dụ `full_r2b`, `full_r3b`), **giữ nguyên** hai thư mục lỗi này để minh bạch.

**L4 – Độ trung thành** — *Mới chuẩn bị mẫu, chưa chấm.*
- Lệnh: `python NCKH/experiments/sample_fidelity.py NCKH/experiments/results/full_r1 --n 50 --seed 42` (script mới).
- Pool 439 câu rút gọn của V4; lấy 50 câu. Đầu ra: `results/full_r1/fidelity_sample.csv`, `fidelity_scores.csv` (cột chấm để trống).
- Cần 2 người (Sang, Thiện) chấm **độc lập** (2 = đủ ý, 1 = mất ý phụ, 0 = mất/sai ý chính).

**L5 – MOS** — *Không thực hiện:* cần video gốc để chấm độ khớp hình và cần 8–15 người nghe; hiện chỉ có audio.

**L6 – Cấu hình máy** — *Xong* (mục 1; mạng chưa đo).

**S1–S5 (server)** — *Không thực hiện:* cần Sang cung cấp thông tin mục 7.B, và S4 cần Sang cho phép bằng lời. Đã đề xuất cách đọc DB
(SELECT, chạy trong container `lms_mysql`, DB `lms_db`, user `lms_user`, người chạy tự nhập mật khẩu); **chưa chạy**.

## 4. Kết quả

### 4.1. So sánh V1–V4 (`results/full_r1/summary.json`, n = 787 câu, 1 lần chạy)

| Phương án | run | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % còn tràn | % R>1,3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|---|
| V1 một pha | full_r1 | 787 | 1,649 | 1,544 | 3,46 | 94,0 | 75,6 | 7 | 787 |
| V2 hai pha | full_r1 | 787 | 1,093 | 1,024 | 2,632 | 84,2 | 55,8 | 14 | 787 |
| V3 hai pha + tăng tốc | full_r1 | 787 | 0,392 | 0,144 | 1,328 | 54,9 | 25,3 | 14 | 677 |
| V4 đề xuất | full_r1 | 787 | 0,190 | 0,016 | 0,916 | 26,7 | 17,0 | 690 | 2097 |

Tổng thời gian tràn (s) / tràn mỗi phút lời thoại (s): V1 1297,5 / 27,36; V2 860,2 / 18,14; V3 308,6 / 6,51; V4 147,5 / 3,11.
Tham chiếu đợt 1 (603 câu, chỉ 10 phút đầu mỗi bài, `results/20261109_042122/`): V4 Δ TB 0,157 s, 23,5% còn tràn, 13,8% R>1,3.
Khác biệt giữa hai đợt chưa thể quy cho nguyên nhân nào (khác tập câu, LLM không tất định) — chờ L3 để biết độ dao động.

**Chỉ có 1 lần chạy hoàn chỉnh** (`full_r1`), nên chưa có độ dao động giữa các lần chạy; mọi con số trên là 1 mẫu. L3 thất bại (mục 3), chưa có trung bình ± độ lệch chuẩn.

### 4.2. Phân bố nhánh của V4 và phân bố R (`summary.json`)

V4: rút gọn (`summarize`) 264 câu (33,5%), tăng tốc 233 (29,6%), chạm trần +30% (`capped`) 175 (22,2%), đệm lặng 115 (14,6%).
Phân bố R mặc định sau pha 2: R ≤ 1,0: 14,0%; 1,0 < R ≤ 1,3: 30,2%; R > 1,3: 55,8%. R trung bình mặc định V1/V2 = 1,640/1,472.
Độ dài câu dịch trung bình (ký tự): V1 70,2; V2 57,7; V4 47,8.

### 4.3. Kiểm tra toàn bộ độ dài trên audio thật (`results/full_r1/check_full_length.md`, `drift_measured.csv`)

| Video | Phương án | Gốc (s) | Sau ghép (s) | Chênh (s) | Chênh (%) | Trễ mốc câu TB / p95 / max (s) | % câu trễ >1 s |
|---|---|---|---|---|---|---|---|
| lec01 | V2 | 566,0 | 695,14 | +129,14 | +22,82 | 66,72 / 118,66 / 127,74 | 98,5 |
| lec01 | V4 | 566,0 | 575,41 | +9,41 | +1,66 | 3,11 / 6,81 / 8,01 | 70,2 |
| lec02 | V2 | 815,1 | 1093,03 | +277,93 | +34,10 | 130,81 / 261,42 / 277,12 | 98,4 |
| lec02 | V4 | 815,1 | 833,39 | +18,29 | +2,24 | 8,08 / 15,79 / 17,50 | 98,4 |
| lec03 | V2 | 718,0 | 898,28 | +180,28 | +25,11 | 91,53 / 169,32 / 186,11 | 98,9 |
| lec03 | V4 | 718,0 | 761,50 | +43,50 | +6,06 | 7,76 / 18,01 / 22,09 | 89,5 |
| lec04 | V2 | 900,0 | 1063,54 | +163,54 | +18,17 | 72,11 / 142,76 / 164,04 | 92,4 |
| lec04 | V4 | 900,0 | 995,89 | +95,89 | +10,65 | 43,07 / 82,17 / 95,92 | 99,0 |

Thời lượng từng đoạn V4 (khung → sau ghép, giây): lec02 600 → 611,98 và 215 → 221,41; lec03 600 → 612,69 và 118 → 148,81;
lec04 600 → 654,87 và 300 → 341,01 (đầy đủ trong `check_full_length.json`). **Không có đoạn nào ghép ra đúng bằng khung đoạn.**
Đối chiếu với ước lượng từ CSV (`drift_summary.md`): chênh cuối video V4 ước lượng 9,41 / 18,39 / 22,09 / 95,96 s so với đo thật 9,41 / 18,29 / 43,50 / 95,89 s;
lệch ở `lec03` do câu ASR bất thường (mục 5, điểm 2).

### 4.4. Độ trung thành câu rút gọn (L4)
Chưa chấm. Đã có mẫu 50 câu (seed 42) ở `results/full_r1/fidelity_sample.csv`. Ví dụ trong dữ liệu đợt 1: câu gốc *"Thought Cafe."* được V4 rút thành *"Tư duy"*
(mất "Cafe") — đây chỉ là ví dụ, chưa phải kết luận.

### 4.5. MOS (L5)
Không thực hiện.

### 4.6. Server (S1–S3), 4.7. Cấu hình server (S5)
Không thực hiện — chờ Sang cung cấp thông tin và cho phép.

## 5. Điểm bất thường và nghi vấn

1. **Audio lồng tiếng dài hơn bản gốc và trễ cộng dồn** (mục 4.3). Cơ chế (đọc từ [dubbing_service.py](../../../app/services/dubbing_service.py)):
   khoảng lặng trước mỗi câu bằng `seg.start − prev_end` của bản gốc, cố định; câu dài hơn khung được chèn nguyên độ dài, câu sau bị đẩy lùi
   và không bù lại; `trailing_gap = max(0, chunk.end − prev_end)` không bao giờ âm; các đoạn nối bằng `concat_files` không cắt. Hệ quả:
   thời lượng đoạn = khung + tổng phần tràn. **Mâu thuẫn với bài báo** ("âm thanh của mỗi đoạn có thời lượng đúng bằng L … không tích lũy độ trễ giữa các đoạn").
   Chỉ số Δ = |t_final − t_orig| theo từng câu **không phản ánh** độ trễ này; cần chỉ số trễ mốc câu (`drift_analysis.py`, `check_full_length.py`).
   Cần nhóm quyết định: sửa pipeline (bù/cắt khoảng lặng để về mốc gốc) hay sửa mô tả trong bài. Chưa kiểm chứng trên `final.mp3` thật của server.
2. **ASR cho mốc vượt hết audio ở `lec03`:** câu cuối seq 181 *"Thank you."* có mốc 709,44 → 739,42 s trong khi audio dài 718,0 s
   (`.cache/lec03/asr_cache.json`; `.cache` không commit — mốc này cũng nằm trong cột `t_orig` của `segments.csv`, `t_orig` ≈ 29,98 s). Pipeline không giới hạn mốc theo thời lượng
   audio nên đoạn cuối dài thêm khoảng 21 s do đệm lặng. Bỏ câu này thì chênh cuối video V4 của `lec03` ≈ 22 s (khớp ước lượng 22,09 s).
   Đây là lỗi dữ liệu/ASR gặp thật, có thể xảy ra ở video thật.
3. **Nhãn nhóm sai:** `lec03`, `lec04` gắn `KyNangMem` nhưng nội dung là CNTT; chưa có bài kỹ năng mềm. Bài báo ghi thực nghiệm trên "CNTT và kỹ năng mềm".
4. **`lec04` trễ nhiều nhất** (V4 +95,89 s, +10,65%; speech_ratio 0,875; 290 câu; đây là bài giảng trong lớp, nói tự nhiên, khác với 3 bài Crash Course có kịch bản).
   Chênh lệch về phong cách nói giữa `lec04` (bài giảng trong lớp) và ba bài Crash Course (có kịch bản) chỉ là **suy đoán chưa kiểm chứng**; không kết luận nguyên nhân, cần thêm dữ liệu.
5. **Số liệu thời gian xử lý local** (`v4_adaptive_sec_per_min` = 126,17; `tts_default_sec_per_min` = 46,84; `translate_sec_per_min` = 10,96; `asr_sec_per_min` = 0,62, `summary.json`)
   đo trên máy dùng chung với hệ thống đang chạy, 2 vCPU, chạy tuần tự từng câu — **không dùng để suy ra hiệu năng server**.
6. **Câu rất ngắn / tên riêng bị rút gọn quá tay** (ví dụ "Thought Cafe." → "Tư duy") — chờ L4 để đo.
7. Khác biệt đợt 1 và `full_r1` (mục 4.1) — cần L3 để biết phần nào do LLM không tất định.
8. Số dư credit Gemini ngày 10/11/2026 trước khi chạy: ₫89.056 (ảnh chụp của Thiện).
9. **Credit Gemini đã hết** (lỗi 402 lúc 20:52 UTC ngày 10/11, sau `full_r1` + một phần `full_r2`). Key này nằm trong biến môi trường của `lms_ai_worker`, container
   cũng phục vụ hệ thống thật. **Chưa kiểm tra** xem các tính năng AI thật (lồng tiếng, trợ lý…) có đang lỗi không và có dùng cùng key/dự án không — cần Sang/Thiện kiểm tra và nạp credit.
   Ngoài ra provider Gemini trong code không phân biệt lỗi 402 (hết credit) với lỗi 5xx: log chỉ báo "network error"/"cooldown", khó chẩn đoán.

## 6. Cách kiểm tra lại

```bash
cd /var/lms/ai-worker            # hoặc thư mục gốc ai-worker
python NCKH/experiments/analyze.py NCKH/experiments/results/full_r1          # bảng 4.1, 4.2 (summary.md/json)
python NCKH/experiments/drift_analysis.py NCKH/experiments/results/full_r1   # ước lượng trễ từ CSV
# Ghép audio thật (cần audio/ của run, tức chạy run với --keep-audio; chạy trong container ai-worker):
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/check_full_length.py NCKH/experiments/results/full_r1 --variants V2,V4
python NCKH/experiments/sample_fidelity.py NCKH/experiments/results/full_r1 --n 50 --seed 42
```
`audio/` và `.cache/` không được commit (đã có trong `.gitignore`), nên mục 4.3 chỉ tái tạo được trên máy đã chạy run.

## 7. Danh sách file (dự kiến commit — chưa commit)

- Script mới: `experiments/drift_analysis.py`, `aggregate_runs.py`, `sample_fidelity.py`, `check_full_length.py`
- `experiments/videos.json` (chỉ sửa `note`)
- `experiments/results/full_r1/` (không gồm `audio/`): `segments.csv`, `videos.csv`, `run_meta.json`, `summary.md/json`, `NOTES.md`,
  `check_full_length.md/json`, `drift_measured.csv`, `drift_summary.md/json`, `fidelity_sample.csv`, `fidelity_scores.csv`
- Run lỗi, giữ để minh bạch: `experiments/results/full_r2/` (chỉ `lec01`), `experiments/results/full_r3/` (không dữ liệu), mỗi thư mục có `NOTES.md` (không gồm `audio/`)
- `experiments/reports/REPORT_20261110_Thien.md` (file này)

## 8. Việc cần Thiện và Sang quyết định (hội ý 11/11)

0. **Ưu tiên cao nhất — credit Gemini đã hết:** kiểm tra tác động lên hệ thống thật, nạp credit, rồi mới chạy lại L3 (`full_r2b`, `full_r3b`, V2 và V4).
   Số dư ₫89.056 đã hết sau `full_r1` (690 lần gọi LLM cho V4 + 14 lần dịch) và một phần `full_r2`. **Chưa có số đo chi phí chính xác** cho từng run;
   cần xem bảng chi phí trên AI Studio để biết cần nạp bao nhiêu cho L3 (V2+V4 × 2 lần) trước khi chạy lại.
1. **Dữ liệu:** thêm ≥ 2 bài kỹ năng mềm (và cần file video nếu muốn đo độ khớp hình), hay sửa nhãn/câu mô tả trong bài thành "lĩnh vực CNTT"? Xác minh giấy phép 4 bài.
2. **Độ trễ cộng dồn (mục 5.1):** sửa pipeline hay sửa mô tả trong bài? Thêm chỉ số trễ mốc câu vào bài?
3. **Câu ASR vượt mốc audio (mục 5.2):** có cần chặn mốc theo thời lượng audio trong pipeline không?
4. **Chạy thật qua web (S4):** Sang cho phép chưa; server có cấu hình proxy YouTube chưa (code ghi YouTube chặn IP VPS), hay upload file video; hạn ngạch 15 job/ngày/học viên (30 giảng viên).
5. **S1–S3, S5:** Sang cho biết job nào là test/lỗi cần loại, commit và model server đang chạy; bài B1, B2 khoá Unity và Agent là link YouTube hay file upload, ngôn ngữ gốc là gì.
6. **L4:** ai chấm (Sang, Thiện), khi nào.
7. **Nơi push:** nhánh `NCKH` hay `feat/additional-features`. (Quy tắc dự án cho tự push `feat/additional-features`; hướng dẫn nhóm nói push `NCKH`.)
8. **Chạy chung máy với hệ thống thật** (2 vCPU, 3,7 GiB RAM, còn ~1 GiB): có nên chạy L3 và các đợt sau trên máy khác không?
