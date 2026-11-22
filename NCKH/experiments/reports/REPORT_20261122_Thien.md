# REPORT đo lại sau tối ưu lồng tiếng (đợt 3) — 22/11/2026

Người đo: Thiện. Mục đích: lấy số liệu mới cho bài SSRC-II'2026 (bản chính thức hạn 04/12/2026) trên pipeline đã tối ưu.
Bản mới khác bản cũ: một lời gọi dịch có `max_chars`, tăng tốc `atempo` (không gọi lại TTS), rút gọn theo lô, mốc đầu câu theo từ đầu tiên, Gemini 3.6 Flash (thinking `minimal`), nhạc nền bật, dây chuyền 2 công đoạn.
Không sửa `paper/main.tex`. Mọi số dưới đây truy được về file trong `NCKH/experiments/results/` (xem mục 7).

## 0. Tóm tắt cho người duyệt (Sang)

1. Thứ tự các phương án về độ lệch **vẫn giữ**: V1 (1,89 s) > V2 (1,25 s) > V3 (0,29 s) > V4 (0,19 s) trên 780 câu của 4 bài.
2. V4 giảm mạnh chi phí so với bản cũ: **20 lời gọi LLM và 1.034 lần TTS** (bản cũ `e5a8cb7`: 286 và 1.678).
3. Độ trễ đo trên audio thật (cách ghép mới): V4 |trễ| trung bình **0,11–0,68 s** theo bài (bản cũ: 0,49–4,35 s). Bài `lec04` vẫn là bài tệ nhất.
4. Job thật qua web (C4): 4/4 `COMPLETED`, **11,7–15,8 giây xử lý cho mỗi phút video** (bản cũ: 110,3). **Không so được như nhau** vì điều kiện khác (mục 5).
5. **Khác hướng dẫn gốc:** không xóa dữ liệu cũ (Thiện từ chối bước A6) nên C4 chạy bằng **ko-KR** (giọng SunHi), không phải tiếng Việt. Hệ quả ghi ở mục 5 và 6.
6. Còn thiếu: chấm L4 (Sang + Thiện), số tiền chính xác từng job, thống kê phía DB.

## 1. Môi trường (A0, A4, A5)

| Mục | Trước build lại | Sau build lại |
|---|---|---|
| Commit ai-worker | `0d866b9` | `0d866b9` (`run_meta.json` ghi `?` do container không đọc được git) |
| `GEMINI_MODEL` / `DUBBING_THINKING_LEVEL` / `BGM_SEPARATION` | `gemini-3.6-flash` / `minimal` / `modal` | như trước |
| ffmpeg / Debian | 7.1.5 / (chưa ghi) | 7.1.5 / 13.7 |
| Gói `modal` trong image | **thiếu** (`ModuleNotFoundError`) | có (`modal==1.6.4`), `hydrate()` ok |
| Gọi thử Gemini (A5) | – | `ok` |
| Container | `running` | `running restarts=0 oom=false` |

Cấu hình đo: `TIMELINE_ENGINE=ffmpeg`, `CHUNK_MINUTES=10`, `MAX_RESUMMARIZE_ATTEMPTS=2`, `MIN_RESUMMARIZE_FRAME_SEC=2.0`, `TTS_CONCURRENCY=16`, ASR `whisper-large-v3-turbo`. `GEMINI_MODELS` để trống.
`tts_cps` cuối đợt: HoaiMy 11,052; NamMinh 10,683; SunHi (ko-KR) 4,887 ký tự/giây.
Chi tiết, nhật ký các lần chạy: `results/server_20261122/NOTES.md`.

## 2. Bảng 2 — V1–V4 trên 4 bài (C1), 780 câu, giọng vi-VN

Nguồn: `results/v3_r1_merged/summary.json` (gộp `v3_r1` cho lec02–04 và `v3_r1_lec01b` cho lec01; lý do ở mục 6, bất thường 1).

| Phương án | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1,3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|
| V1 dịch không ràng buộc, tốc độ mặc định | 1,893 | 1,728 | 3,776 | 96,9 | 82,8 | 7 | 780 |
| V2 dịch theo ngân sách thời lượng, tốc độ mặc định | 1,248 | 1,22 | 2,656 | 90,5 | 63,7 | 7 | 780 |
| V3 giới hạn ký tự + atempo, không rút gọn | 0,288 | 0,0 | 1,112 | 46,5 | 23,2 | 7 | 780 |
| V4 đề xuất (đầy đủ) | **0,185** | 0,0 | 0,961 | 30,4 | 19,6 | 20 | 1.034 |

**V4 lần 2** (C2, giọng đã có `tts_cps`; `results/v3_r2/summary.json`): Δ TB 0,194; Δ p95 1,072; % tràn 26,4; % R>1,3 sau 19,0; LLM 21; TTS 845. Sang chọn lần chính; hai lần chênh nhau rất ít.

**Hàng tham chiếu — số CŨ, bản `e5a8cb7`** (`results/post_fix_r1/summary.json`, 787 câu, không trộn với bảng trên):

| Phương án (tên cũ) | Δ TB (s) | % R>1,3 sau | LLM | TTS |
|---|---|---|---|---|
| Dịch một pha, tốc độ mặc định | 1,669 | 75,3 | 7 | 787 |
| Dịch hai pha, tốc độ mặc định | 0,996 | 50,7 | 14 | 787 |
| Hai pha + tăng tốc độ đọc | 0,357 | 23,8 | 14 | 666 |
| Đề xuất (đầy đủ) | 0,216 | 19,9 | 286 | 1.678 |

Lưu ý khi so: số câu khác (780 so với 787) vì ASR mới (mốc đầu câu theo từ đầu tiên) cho ranh giới câu khác; V1 mới (1,89 s) lớn hơn V1 cũ (1,67 s) chưa rõ nguyên nhân (có thể do model mới viết dài hơn); tên phương án mới và cũ không trùng hoàn toàn (V2 cũ là "hai pha", V2 mới là "một lời gọi có ngân sách thời lượng").

**Điều kiện giọng của C1:** chỉ `lec02` và `lec03` chạy khi giọng chưa có `tts_cps`. `lec01` chạy bù sau khi HoaiMy đã có số đo (11,480, từ `lec03`); `lec04` dùng số đo NamMinh từ `lec02` (12,722). Chi tiết từng bài: `results/v3_r1_merged/videos.csv` (cột `cps_before`).

## 3. Bảng 3 — độ trễ theo trục thời gian (C3, audio thật, cách ghép mới)

Nguồn mới: `results/v3_r1_merged/check_full_length.md`. Nguồn cũ: `results/post_fix_r1/check_full_length.md` (ASR cũ, mốc đầu câu kiểu cũ nên **không cùng thước đo hoàn toàn**).

| Bài | V2 mới: \|trễ\| TB (s) | V4 mới: \|trễ\| TB | V4 mới: % trễ >1 s | V4 mới: muộn max (s) | V4 cũ: \|trễ\| TB | V4 cũ: % trễ >1 s |
|---|---|---|---|---|---|---|
| lec01 | 26,6 | 0,11 | 4,6 | 2,08 | 0,49 | 20,6 |
| lec02 | 24,3 | 0,25 | 2,2 | 1,93 | 1,03 | 36,8 |
| lec03 | 8,9 | 0,30 | 7,2 | 3,17 | 0,87 | 22,7 |
| lec04 | 7,1 | 0,68 | 21,6 | 6,41 | 4,35 | 62,8 |

Tổng thời lượng sau ghép khớp bản gốc trong ±0,1 s ở cả 4 bài (V2 và V4).

**Không dùng** `drift_analysis.py` cho Bảng 3: nó là mô hình ước lượng cho cách ghép CŨ (câu chèn nguyên độ dài, trễ cộng dồn; trễ cuối video của V4 lên tới 91 s ở `lec04`). Số này lưu ở `results/v3_r1_merged/drift_summary.md` chỉ để tham khảo; trộn với số đo thật sẽ gây hiểu sai.

## 4. Thời gian xử lý trên máy chạy script (C1, local theo câu)

Từ `results/v3_r1_merged/videos.csv`: dịch 53–73 s/bài (một lời gọi cho mỗi chunk), V4 129–153 s/bài với bài 2 chunk (80,9 s cho `lec01`). Đây là thời gian local chạy tuần tự từng câu, không phải thời gian hệ thống thật.

## 5. Bảng 4 — 4 job thật qua web (C4), ngôn ngữ ko-KR, giọng SunHi

Nguồn: `results/server_20261122/worker_logs.json` (từ `docker logs`, parser `parse_worker_logs.py`). Job 17–20 = lesson 2284, 2285, 2286, 2288; tất cả `COMPLETED` (kết quả Celery `{'status': 'COMPLETED'}`), không thấy dòng thử lại nào trong log (chưa đối chiếu cột `retry_count` ở DB), 0 dòng `HET CREDIT (402)`, 0 lỗi 401/key.

| Job | Bài (dài) | Chunk | Câu | Tới đoạn đầu (s) | Xong (s) | s xử lý / phút video | Upload max (s) |
|---|---|---|---|---|---|---|---|
| 17 | lec01 (9:26) | 1 | 133 | 148,3 | 148,8 | 15,8 | 3,1 |
| 18 | lec02 (13:35) | 2 | 188 | 141,7 | 169,0 | 12,4 | 3,2 |
| 19 | lec03 (11:58) | 2 | 181 | 120,4 | 139,7 | 11,7 | 3,0 |
| 20 | lec04 (15:00) | 2 | 259 | 172,8 | 220,6 | 14,7 | 3,1 |

TIMING từng chunk (giây):

| Job | Chunk | asr | dịch | chờ chunk trước | tts | ghép | nhạc | upload | tổng |
|---|---|---|---|---|---|---|---|---|---|
| 17 | 0 | 0,0 | 24,8 | 0,0 | 83,0 | 4,4 | 23,0 | 3,1 | 138,3 |
| 18 | 0 | 0,0 | 18,9 | 0,0 | 56,7 | 8,1 | 46,4 | 3,2 | 133,3 |
| 18 | 1 | 0,0 | 6,0 | 108,4 | 9,6 | 1,8 | 8,8 | 2,6 | 137,2 |
| 19 | 0 | 0,0 | 13,8 | 0,0 | 40,7 | 5,7 | 50,2 | 3,0 | 113,4 |
| 19 | 1 | 0,0 | 3,3 | 96,2 | 6,5 | 1,0 | 5,1 | 2,4 | 114,6 |
| 20 | 0 | 0,0 | 16,9 | 0,0 | 47,0 | 4,8 | 93,1 | 3,1 | 164,8 |
| 20 | 1 | 0,0 | 9,1 | 138,8 | 26,7 | 2,5 | 12,2 | 2,2 | 191,5 |

- Dây chuyền chạy đúng ở 3 bài nhiều chunk: có `cho_chunk_truoc` (96–139 s), chunk 1 chuẩn bị song song rồi chờ chunk 0; thời gian từ lúc xong đoạn đầu đến lúc xong cả bài chỉ **19–48 s** (bản cũ: 417 s).
- Nhạc nền: cả 4 job **tách mới** (`BGM tach nhac xong`, 4–6 phần chạy song song, 88–136 s tổng, chạy song song với TTS); không có `BGM dung lai`.
- `tts` chunk 0 giảm theo thứ tự chạy (83,0 → 56,7 → 40,7 → 47,0 s) vì giọng SunHi có `tts_cps` sau job 17.

**Số cũ cạnh số mới** (cũ: `results/server_20261113/`, commit `4ab708f`, cùng 4 bài lesson 2284, 2285, 2286, 2288, tiếng Việt `vi-VN`, job 10–13; ASR nằm trong thời gian xử lý):

| Chỉ số | Cũ (13/11) TB | Mới (22/11) TB | Mới: khoảng |
|---|---|---|---|
| Giây xử lý / phút video | 110,3 | 13,7 | 11,7–15,8 |
| Giây tới đoạn đầu tiên | 1.044,8 | 145,8 | 120,4–172,8 |
| Giây giữa 2 đoạn hoàn tất | 417,0 | 31,4 | 19,2–47,7 |
| Số lần thử lại | 0 (DB) | không thấy trong log | – |

**Không được kết luận "nhanh hơn 8 lần" từ bảng này.** Điều kiện khác nhau: (1) mới dùng lại bản ký âm (`asr = 0`), cũ chạy ASR đầy đủ; (2) mới là ko-KR, cũ là tiếng Việt; (3) bản cũ chạy pipeline cũ (commit `4ab708f`: tăng tốc bằng SSML, rút gọn từng câu, chưa có dây chuyền hai công đoạn). Số mới chỉ cho biết hệ thống đạt mức nào trong điều kiện này. Muốn so ngang bằng cần chạy lại tiếng Việt với dữ liệu xóa sạch (bước A6), chưa làm.

## 6. Bất thường (ghi đầy đủ, kể cả lần lỗi)

1. **JSON hỏng ở lời gọi V1.** `smoke_real`, `v3_r1` (lec01) và `v3_r1_lec01` đều lỗi `ProviderError(code='invalid_response')` ở bước dịch (3 trên 5 lần chạy `lec01`); `smoke_real2` và `v3_r1_lec01b` chạy được. Chẩn đoán riêng trên chunk 0 của `lec01`: lời gọi dịch kiểu V2 (`translate_batch`) đúng 4/4 lần, lời gọi V1 (`_build_direct_prompt`) hỏng 1/5 lần, hỏng đúng ở câu "Von Neumann…" (dòng 65–66, chen thừa `", người"`). Chỉ phương án V1 (nền, chỉ có trong script đo) bị ảnh hưởng; pipeline thật không dùng đường này và vẫn có thử lại cả chunk. Đã thêm thử lại tối đa 3 lần cho V1 vào `run_experiment_v2.py`; lần `v3_r1_lec01b` V1 không cần thử lại. Số liệu `lec01` trong Bảng 2 lấy từ `v3_r1_lec01b`.
2. **Lần chạy thử làm bẩn Redis.** `smoke_real2` ghi `tts_cps` của HoaiMy = 13,183 (trước đó cả hai giọng vi-VN đều chưa có khóa). Đã xóa đúng khóa này (Thiện đồng ý) trước C1.
3. **`lec01` chạy sau khi HoaiMy đã có số đo** (11,480 từ `lec03`), nên khác trạng thái "chưa có số đo" của `lec02` và `lec03`.
4. **R > 1,3 sau rút gọn còn nhiều ở tiếng Hàn.** Trong 4 job C4: 151 câu còn `R > 1.3` theo parser (trong job 17, R lớn nhất tôi thấy là 4,32). Job 17 nhiều khả năng là lần đầu SunHi chạy chưa có `tts_cps` (chưa kiểm tra khóa Redis này trước job 17), nên bản dịch không bị giới hạn ký tự, `tts` 83,0 s (cao hơn mức tham khảo khoảng 60 s). Từ job 18 trở đi `tts` chunk 0 còn 40,7–56,7 s.
5. **`lec04` là bài tệ nhất của V4:** |trễ| TB 0,68 s, 21,6% câu trễ trên 1 s, 11,0% trên 2 s, muộn tối đa 6,41 s (bản cũ: |trễ| TB 4,35 s, 62,8% câu trễ trên 1 s). Tỉ lệ có tiếng nói của bài chỉ 0,785, thấp hơn các bài khác (0,909–0,92); chưa kiểm chứng đó là nguyên nhân.
6. **Mốc câu của job thật là mốc cũ.** Cả 4 job dùng lại bản ký âm lưu trước 21/11 (mốc đầu đoạn), nên C4 không phản ánh mốc theo từ đầu tiên. C1–C3 thì dùng ASR mới.
7. **`run_meta.json` ghi `commit: "?"`** (container không có git); commit thật `0d866b9` ghi ở NOTES.
8. **Cột `tgt_v2` trong `fidelity_sample.csv` chứa văn bản V3** (bản dịch đầy đủ trước rút gọn), vì lấy mẫu với `--baseline V3`; tên cột là hằng của script.
9. **Không có:** câu bị loại vì chỉ có dấu câu (`n_unspeakable = 0` cả 4 bài), đoạn bị bỏ vì ít tiếng nói (0), `HET CREDIT (402)` (0), lỗi tách nhạc (0).

## 7. Cách kiểm tra lại (tái tạo từng con số)

Chạy trong container: `docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/...`

| Số | Lệnh / nguồn |
|---|---|
| Bảng 2 (C1) | `run_experiment_v2.py --manifest NCKH/experiments/videos.json --run-id v3_r1 --keep-audio` (và `--only lec01 --run-id v3_r1_lec01b`), gộp thành `v3_r1_merged`, rồi `analyze.py results/v3_r1_merged` |
| V4 lần 2 (C2) | `run_experiment_v2.py --manifest NCKH/experiments/videos.json --run-id v3_r2 --variants V4 --keep-audio`, rồi `analyze.py results/v3_r2` |
| Bảng 3 (C3) | `check_full_length.py results/v3_r1_merged --variants V2,V4 --assembly new` (thư mục `audio/` của bản gộp là liên kết tượng trưng tới audio của `v3_r1` và `v3_r1_lec01b`) |
| Mô hình trễ cộng dồn (không dùng cho Bảng 3) | `drift_analysis.py results/v3_r1_merged` |
| Mẫu L4 (C5) | `sample_fidelity.py results/v3_r1_merged --n 50 --seed 42 --min-frame 2.0 --baseline V3` |
| Bảng 4 (C4) | `docker logs --timestamps --since 2026-11-22T14:44:00Z lms_ai_worker 2>&1 \| python3 -I NCKH/experiments/parse_worker_logs.py --out results/server_20261122/worker_logs.json` (log docker có thể bị xoay vòng theo cấu hình `max-size 10m`, nên `worker_logs.json` là bản lưu chính) |
| Số cũ | `results/post_fix_r1/summary.json`, `results/post_fix_r1/check_full_length.md`, `results/server_20261113/server_summary.md` |

Không commit `audio/`, `.cache/`, `.cache_old_e5a8cb7/`, `media/`, video.

## 8. L4 (độ trung thành nội dung) — chưa chấm

Đã chọn **50 câu** (trong 165 câu rút gọn, `seed 42`, khung từ 2,0 s) tại `results/v3_r1_merged/fidelity_sample.csv`; file điểm trống `fidelity_scores.csv` (0 = mất hoặc sai ý chính, 1 = mất ý phụ, 2 = đủ ý). Sang và Thiện chấm độc lập, mỗi người một bản sao, sau đó thống nhất câu lệch như lần trước. Chưa có số L4 mới nên Tóm tắt, Kết luận phần L4 vẫn giữ `\todo`.

## 9. Chi phí

Chưa có số tiền chính xác cho từng job (bảng `ai_usage_logs` chưa được truy vấn vì cần mật khẩu MySQL). Ước tính cho job 17 (Gemini 3.6 Flash, 0,75 USD vào / 3,75 USD ra mỗi triệu token) khoảng 900đ, dựa trên giả định số token, **không phải số đo**. Số chính xác lấy bằng câu lệnh SQL trong NOTES hoặc trang AI Analytics của admin; chưa điền vào bài.

## 10. Việc còn lại trước 04/12

- [ ] Sang và Thiện chấm L4 (50 câu).
- [ ] Sang kiểm tra REPORT, chọn lần V4 chính (C2).
- [ ] Quyết định có chạy lại C4 bằng tiếng Việt (cần xóa dữ liệu 4 bài theo A6) để so ngang với số cũ không.
- [ ] Lấy số tiền chính xác từ `ai_usage_logs` nếu bài cần nêu chi phí.
- [ ] Điền số vào Bảng 2–4, Tóm tắt, Kết luận trong `paper/main.tex` (Sang làm).
