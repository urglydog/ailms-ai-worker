# REPORT – Thiện – 11/11/2026 — Tình hình thực nghiệm và các câu hỏi gửi Sang

## ✅ TRẢ LỜI CỦA SANG (11/11/2026) — Thiện đọc phần này trước

Sang đã đọc report; số liệu §4.1 và §4.4 đã được tính lại độc lập từ `full_r1/segments.csv` và **khớp**.
E3, E6, E7 đã được đối chiếu với code và **xác nhận đúng**.

| Câu | Quyết định |
|---|---|
| **1a** | **A — đã sửa code.** Câu được xếp theo mốc tuyệt đối `onset_i = max(start_i, onset_{i-1} + dur_{i-1})` (không chồng câu, trễ không cộng dồn). Cuối đoạn: đệm lặng nếu ngắn; nếu dài hơn khung thì tăng tốc **cả đoạn** bằng FFmpeg `atempo` tối đa ×1,15, phần còn dư mới cắt → mỗi đoạn **đúng** `L` = 600 s, không lan sang đoạn sau. Code: `app/audio_utils.py` (`plan_onsets`, `place_on_timeline`, `MAX_CHUNK_TEMPO`), `app/services/dubbing_service.py`. |
| **1b** | **(ii) — đã sửa (chốt 11/11).** Câu có khung gốc `t_orig < 2 s` **vẫn được lồng tiếng** nhưng **không gọi LLM rút gọn**; đi thẳng tăng tốc tối đa +30%, phần dư mượn khoảng lặng phía sau (nhờ 1a). Ngưỡng ở config `MIN_RESUMMARIZE_FRAME_SEC` (mặc định 2.0; đặt 0 để tắt). `run_experiment.py` gọi đúng hàm của pipeline nên **V4 tự dùng hành vi mới**; `run_meta.json` ghi thêm `min_resummarize_frame_sec`. Kỳ vọng giảm ~một nửa lời gọi rút gọn — Thiện báo cáo số lời gọi LLM trước/sau. Gộp mảnh ngắn (i) để làm sau. |
| **1c** | **Có — đã sửa.** Mốc ASR được kẹp trong `[0, độ dài thật của đoạn]`, bỏ câu có `start` ≥ độ dài audio hoặc dài < 0,05 s (`clamp_stt_segments`). Transcript dùng lại từ DB cũng được kẹp `end` theo biên đoạn. |
| **1d** | (i) **Có — đã sửa:** `gemini.py` nhận diện HTTP 402 / "prepayment credits are depleted", log `HET CREDIT (402)`, khoá slot 1 giờ; lỗi 5xx khác giờ cũng log mã lỗi. (ii) **Không** đổi `thinkingBudget` trong đợt này. |
| **1e** | Sang xác nhận sau. Thiện ghi commit mới (sau khi pull bản sửa) vào NOTES của đợt đo lại. |
| **Câu hỏi 2** | Đồng ý bảng T1–T10. Sang đã sửa `main.tex`: T1 (bỏ "luôn khớp… vẫn tự nhiên"), T2 (viết lại mục Ghép âm thanh theo cơ chế mới, công thức `eq:onset`), T7 (đổi thành "4 bài CNTT, 50 phút, 787 câu"); thêm độ đo **trễ theo trục thời gian** (P1). T4, T5 vẫn cần L4. T8, T9 cần S1, S3. |
| **P1, P2, P6, P7, P8** | OK. Commit chốt để đo = commit chứa bản sửa ngày 11/11 trên nhánh `NCKH`. |
| **P3** | Xem 1b. **P4: không làm** (sửa bài thành lĩnh vực CNTT). **P5:** chờ Sang quyết định (Q4/Q9). |
| **Q5** | Sửa mô tả bài thành **CNTT**; không thêm video kỹ năng mềm. |
| **Q6** | Chưa cần xác minh giấy phép lúc này. |
| **Q7** | **Sẽ nạp credit.** ⚠️ Thiện đã chạy đo trong container `lms_ai_worker` của hệ thống thật và dùng hết credit của key dùng chung → Sang kiểm tra lại tính năng AI thật. |
| **Q4, Q9** | **Chạy TẤT CẢ trên server** (cả chất lượng lẫn thời gian) để số liệu thống nhất. Hệ thống mới ở giai đoạn test, chưa có người dùng thật nên được phép. **Cho phép S4**: lồng tiếng thật các bài thử nghiệm qua web (khoá học tạm) để lấy luôn số liệu job thật; ưu tiên dùng **chính các job này** để đo cả chất lượng (từ `transcript_segments`: `speech_rate`, `was_summarized`) và thời gian (`ai_jobs`, `audio_chunks`). Script `run_experiment.py` (V1–V4) cũng chạy trên server. Nhớ deploy bản sửa 11/11 trước khi đo và ghi commit vào NOTES. |
| **Q8** | Job test/lỗi cần loại do **Thiện tự xác định** dựa trên phần đo của mình; ghi danh sách job bị loại và lý do vào report này. **Không xoá** dữ liệu/nội dung cũ của Thiện, chỉ ghi bổ sung. |
| **Q7 (kiểm tra)** | **Thiện kiểm tra** sau khi Sang nạp credit: lồng tiếng, AI Tutor, sinh học liệu, Course Discovery có chạy lại bình thường không; xem log `lms_ai_worker`/`lms_ai_api` từ 10/11 20:52 UTC có lỗi `HET CREDIT (402)` hoặc job FAILED không. Ghi kết quả vào report. |
| **Q10** | Sang tự merge `NCKH` → `develop` sau khi push. |
| **MOS (L5, T4)** | **CÓ LÀM** (chốt 11/11). Làm trên audio của **bản code đã sửa** (sau deploy), không dùng audio `full_r1` cũ. Chi tiết ở mục "Kế hoạch MOS" ngay dưới. |

### Kế hoạch MOS (chốt 11/11)
- **Mục tiêu:** kiểm chứng luận điểm T4 — lồng tiếng sau điều chỉnh tốc độ vẫn **tự nhiên, dễ hiểu và khớp hình**.
- **So sánh:** V2 (hai pha, tốc độ mặc định, không điều chỉnh) vs V4 (đề xuất). Có thể thêm 1 clip **gốc tiếng Anh** mỗi bài làm mốc tham chiếu (không chấm "dễ hiểu").
- **Clip:** 20 đoạn, mỗi đoạn **15–25 giây** (nhiều câu liên tiếp, đủ để cảm nhận độ khớp; không dùng 1 câu lẻ),
  phân tầng: mỗi bài 5 đoạn, ưu tiên đoạn có câu ở nhánh speedup / summarize / capped / câu ngắn < 2 s.
  Mỗi đoạn 2 phiên bản (V2, V4) → **40 clip**. Seed chọn đoạn cố định (vd 42), ghi vào NOTES.
- **Có hình:** tải video gốc YouTube (chỉ đoạn cần, `yt-dlp --download-sections`), ghép audio lồng tiếng đã **ghép theo
  timeline mới** (`audio_utils.place_on_timeline`) đúng khoảng thời gian: 
  `ffmpeg -ss <start> -to <end> -i video.mp4 -i dub.mp3 -map 0:v -map 1:a -c:v libx264 -shortest clip.mp4`.
  Video chỉ dùng nội bộ để chấm, **không đăng công khai**.
- **Người nghe:** **10–15 người** (sinh viên, nghe được tiếng Việt), không thuộc nhóm tác giả. Ghi số người, không thu thập
  tên/email (chỉ mã P01, P02…).
- **Phiếu:** Google Form, mỗi clip chấm thang **1–5**: (1) Độ tự nhiên của giọng đọc; (2) Độ dễ hiểu; (3) Độ khớp giữa
  tiếng và hình. Thứ tự clip **xáo trộn** cho mỗi người (hoặc 2 phiếu thứ tự khác nhau), **không** ghi tên phương án.
  Có 2 clip luyện tập ở đầu (không tính điểm). Mỗi người ~15 phút.
- **Phân tích:** MOS trung bình ± KTC 95% từng tiêu chí cho V2 và V4; kiểm định **Wilcoxon theo cặp** (theo đoạn, trung
  bình điểm các người nghe) — báo p-value; số người bị loại (nếu chấm toàn một mức / bỏ dở) và lý do.
- **File lưu:** `results/mos/clips_key.csv` (mã clip → đoạn, phương án; KHÔNG gửi người nghe),
  `results/mos/mos_responses.csv` (đã ẩn danh), `results/mos/NOTES.md` (seed, cách chọn đoạn, link form không công khai),
  script chọn đoạn + ghép clip + phân tích commit kèm. **Không commit video/audio.**
- **Thời hạn:** gửi form chậm nhất **13/11**, chốt kết quả **14/11** → ghi vào report (mục 4.5) để Sang kiểm tra.

### Việc Thiện làm tiếp (không tốn API)
1. Pull nhánh `NCKH` (đã có bản sửa code + test `tests/test_timeline.py`; toàn bộ test ai-worker: 57 passed).
2. **Sửa `check_full_length.py`** để ghép bằng `audio_utils.place_on_timeline` (cách mới) **bên cạnh** cách cũ, chạy lại trên
   `full_r1` (file câu đã lưu, `--keep-audio`) cho V2 và V4. Báo cáo cả hai: tổng thời lượng so với gốc, trễ mốc câu
   TB/p95/max, % câu trễ > 1 s và > 2 s, số đoạn phải tăng tốc và hệ số `tempo_applied`, số đoạn bị cắt phần dư.
   Lưu ý: kết quả mới cần **kẹp mốc ASR (1c)** khi dựng lại mốc từ `asr_cache.json` cho đúng với code.
3. Chấm L4 (`fidelity_sample.csv`) cùng Sang.
4. Sau khi Sang nạp credit và bản sửa đã deploy: kiểm tra Q7, rồi chạy đo trên server theo Q4/Q9 (S4 + V1–V4 + S1–S3).
   Ghi job bị loại (Q8) vào report.

## 📝 THIỆN PHẢN HỒI LẦN 2 (12/11/2026) — Sang đọc phần này tiếp

**Đã làm sau khi Sang trả lời (không cần credit Gemini):**
1. **Kiểm tra bản sửa của Sang trên code và dữ liệu `full_r1`.** Đọc `audio_utils.py`, `dubbing_service.py`, `gemini.py`: đúng như mô tả. Test chức năng riêng
   (`plan_onsets`, `clamp_stt_segments`, `place_on_timeline` trong container): **đúng**, đoạn luôn đúng độ dài, tăng tốc chặn ở ×1,15. Container **không cài `pytest`**
   nên Thiện chưa chạy được bộ test của Sang (57 passed là số của Sang).
2. **Đã deploy (12/11 16:02 UTC):** file mới có trên đĩa từ 15:23 nhưng `lms_ai_worker` chạy từ 09/11 nên đang dùng code cũ; Thiện đã **restart `lms_ai_worker`** (worker rảnh, không task nào đang chạy;
   không đụng DB/volume/BE/FE; `lms_ai_api` chạy `--reload` nên đã tự nạp code mới). Kiểm tra sau restart: worker trả lời ping, `place_on_timeline`/`clamp_stt_segments` có mặt,
   `min_resummarize_frame_sec = 2.0`, `MAX_CHUNK_TEMPO = 1.15`, commit `e5a8cb7` (chứa bản sửa 11/11 của Sang); RAM worker ~308 MB, CPU ~0%, `RestartCount=0`, không OOM.
   **Lưu ý vận hành:** 3 container ai-worker dùng `json-file` **không giới hạn dung lượng log** (hiện nhỏ: worker ~51 KB, api ~20 KB). Nên đặt `max-size` trong file compose
   của `/var/lms/be` (Thiện chưa tự đổi vì là cấu hình hệ thống). Ngoài ra `lms_ai_api` (`--reload`) tự khởi động lại mỗi khi có file Python đổi trong `/var/lms/ai-worker`, kể cả `NCKH/experiments/*.py`
   (đã thấy ~26 lần) — nên loại thư mục `NCKH/` khỏi danh sách theo dõi.
3. **Dự đoán từ dữ liệu `full_r1`** (xếp mốc tuyệt đối + quy tắc câu ngắn, pad nhúng sẵn trong file câu như code thật): trễ tối đa V4 ≈ **8,5 / 5,5 / 1,5 / 16,1 s**
   (đo hiện tại 8,0 / 17,5 / 22,1 / 95,9 s); phần đuôi bị cắt ≈ 0; **tăng tốc cả đoạn 1,00–1,08**. Trễ trung bình có chỗ **âm** (`lec03` ≈ −1,3 đến −1,6 s: tiếng *sớm* hơn hình)
   vì tăng tốc nén cả đoạn. Tổng thời gian tràn theo câu của V4 tăng 147,5 s → ~176,9 s (+20%, vì câu < 2 s không còn được rút gọn) nhưng lời gọi rút gọn giảm
   676 → ~316 (cả run V4 ≈ 330 lần gọi so với 690) → chi phí một lượt V4 ≈ **36K₫** (giả định ~109₫/lần gọi). Đây là **dự đoán**, chưa phải đo trên bản đã deploy.
4. **Hệ thống thật:** log `lms_ai_worker`/`lms_ai_api`/`lms_backend` từ 10/11 20:52 UTC **không có** lỗi Gemini do hết credit (chưa có lưu lượng AI thật chạm key; log docker có thể bị giới hạn lưu).
5. **Đã chuẩn bị sẵn để nạp credit xong là chạy** (script trong `NCKH/experiments/`, đã chạy thử trên dữ liệu giả hoặc `full_r1`):
   `check_full_length.py` (ghép cách cũ/mới, trễ có dấu và tuyệt đối, tempo, cắt đuôi) · `sample_fidelity.py --min-frame 2.0` + `score_fidelity.py` (L4; **mẫu mới
   `results/full_r1/fidelity_sample_v2.csv` gồm 50 câu khung ≥ 2 s, chọn từ 251 câu — Sang và Thiện có thể chấm ngay**) · `mos_select_clips.py`, `mos_make_clips.py`,
   `mos_analyze.py`, `mos_form_template.md` (MOS) · `server_job_stats_ext.sql`, `analyze_server.py`, `parse_worker_logs.py` (S1–S3, chỉ đọc, không lấy email/tên/URL).
6. **Kết quả ghép audio thật, cách mới so với cách cũ** (`results/full_r1/check_full_length.md`; audio của `full_r1` — V4 là hành vi cũ, câu ngắn vẫn bị rút gọn):

   | Video | V4 cũ: chênh (s) / trễ max (s) | **V4 mới: chênh (s) / muộn max / sớm max (s)** | tempo cả đoạn | % \|trễ\| > 2 s (cũ → mới) | V2 mới: cắt đuôi (s) |
   |---|---|---|---|---|---|
   | lec01 | +9,41 / 8,01 | **0,0** / 7,92 / 0,06 | 1,000 | 61,1 → 60,3 | 18,3 |
   | lec02 | +18,29 / 17,50 | **−0,1** / 5,52 / 4,09 | 1,009 | 93,5 → 29,7 | 114,6 |
   | lec03 | +43,50 / 22,09 | **0,0** / 1,19 / 3,52 | 1,042 | 85,1 → 32,6 | 51,4 |
   | lec04 | +95,89 / 95,92 | **0,0** / 15,37 / 3,54 | 1,013 | 94,1 → 67,2 | 0,03 |

   - Cách mới: **tổng thời lượng đúng bằng bản gốc ở cả 4 bài**; trễ muộn tối đa của V4 giảm mạnh (lec04: 95,9 → 15,4 s; lec03: 22,1 → 1,2 s); phần đuôi bị cắt của V4 ≈ 0; tempo cả đoạn thực tế chỉ
     1,00–1,04 (dự đoán trước đó 1,08 là quá cao). Còn **~60–77% câu lệch > 1 s** ở `lec01`, `lec04` (độ lệch nhỏ nhưng dai dẳng, chủ yếu do câu tràn ở đầu bài/đoạn dày lời) — cần báo trung thực trong bài.
   - Có chỗ tiếng **sớm** hơn hình (`lec02`: sớm tối đa 4,1 s, `lec03`: 3,5 s) do tăng tốc cả đoạn nén thời gian → chỉ số trong bài nên báo cả trễ có dấu và \|trễ\|.
   - **V2 (không điều chỉnh) dưới cách ghép mới bị cắt đuôi rất lớn** (lec02 mất 114,6 s ≈ 14% nội dung vì dư quá ×1,15): V2 dùng trong MOS sẽ nghe trễ nặng và có thể mất đoạn cuối; đây đúng là hành vi
     "không điều chỉnh" nhưng Sang cần biết khi mô tả đường cơ sở V2 trong bài và khi chọn đoạn MOS (nên chọn đoạn ở phần đầu mỗi chunk để V2 chưa bị cắt).
   - Cách cũ khớp bảng §4.2 (V4: +9,41 / +18,29 / +43,50 / +95,89 s), xác nhận công cụ đo ổn định.

### Cập nhật 13/11/2026 (sau khi Sang trả lời N1–N5) — Thiện

- **Credit:** Thiện đã nạp, số dư 143K₫. Gọi thử Gemini (1 từ) thành công; lưu ý lời gọi 1 từ vẫn tốn **5 token "suy nghĩ" ẩn** (`thoughtsTokenCount`), phù hợp giả thuyết đơn giá cao do token suy nghĩ.
- **N1 đã deploy + N4 đã làm (13/11 09:53 UTC):** `docker compose up -d --no-deps ai-api ai-worker ai-beat` (chỉ 3 container ai bị tạo lại; worker rảnh; không đụng DB/volume/BE/FE). Sửa `/var/lms/be/docker-compose.yml`
  (file này **chưa commit trong repo `be`**, ngoài ra còn 1 dòng `LMS_PAYOUT_ENCRYPTION_KEY` chưa commit từ trước, không phải của Thiện):
  (1) thêm `logging: json-file, max-size 10m, max-file 3` cho `ai-api`, `ai-worker`, `ai-beat`; (2) `ai-api`: thêm `--reload-dir /app/app --reload-exclude "NCKH/experiments/*"`.
  **Lưu ý:** `--reload-dir` một mình **không đủ** (uvicorn vẫn reload vì file trong `NCKH/`), phải thêm `--reload-exclude`. Đã kiểm chứng: chạm file trong `NCKH/experiments/` → 0 lần reload; chạm file trong `app/` → vẫn reload (đối chứng).
  Sao lưu compose trước khi sửa. Kiểm tra sau áp dụng: cả 3 container `running`, `RestartCount=0`, không OOM; worker nạp code N1 (không còn `pad_silence` trong file câu), `min_resummarize_frame_sec=2.0`; commit `4ab708f`.
- **Run đo sau bản sửa (`post_fix_r1`, V1–V4, 4 bài, `--keep-audio`) đang chạy** từ 09:53 UTC trong container `lms_ai_worker` (uid 1000), bản code `4ab708f`. **Bài đầu `lec01` đã qua kiểm tra:** không lỗi, không 402; câu khung < 2 s **0 lần rút gọn** (đúng quy tắc);
  không câu nào có `t_final < t_orig`; lời gọi rút gọn V4 79 → 71 (bài ngắn); nhánh V4: pad 8, speedup 67, summarize 52, capped 4 (trước: pad 17, speedup 57, summarize 41, capped 16); tổng tràn theo câu V4 = 9,9 s (như trước).
- **Khóa học thử nghiệm đã tạo:** khóa **92** "Nền tảng khoa học máy tính" (Nháp, không gửi duyệt), 4 bài đã up mp4 (khớp thời lượng audio ±0,04 s): `lec01` = lesson **2284**, `lec02` = **2285**, `lec03` = **2286**, `lec04` = **2288**
  (lesson 2287 cũng từng xuất hiện trong log với tên `lec04` — Thiện cần xác nhận đó là bản trùng đã xoá). **Chưa bấm lồng tiếng** vì run `post_fix_r1` đang dùng chung máy/API; sẽ chạy 4 job web sau khi run xong để số thời gian server không bị nhiễu.
- **Phát hiện ngoài phạm vi thí nghiệm (Q7):** 12 tác vụ `embed_course` cho khóa 92 lỗi `[Errno -2] Name or service not known` — host Supabase vector `esiyaricxvhucimtrdqn.supabase.co` **không phân giải được tên** từ server (cả `lms_ai_api`, cả máy host), trong khi Gemini/Groq/Redis/backend bình thường. Nghi project Supabase bị tạm dừng hoặc xoá;
  ảnh hưởng: đánh chỉ mục khóa học (Course Discovery) và RAG của AI Tutor; **không ảnh hưởng lồng tiếng** (lỗi ở bước này bị bắt riêng). **Sang kiểm tra dashboard Supabase** (khôi phục nếu bị tạm dừng). Không do restart/sửa compose (cấu hình môi trường không đổi).

**Việc cần Sang làm:** (a) trả lời 5 câu hỏi dưới đây, (b) nạp credit Gemini, (c) chấm L4 với Thiện (`fidelity_sample_v2.csv`, điểm 2/1/0 vào `fidelity_scores_v2.csv`, mỗi người một cột).

**Năm câu hỏi mới cho Sang**

| # | Câu hỏi | Trả lời của Sang |
|---|---|---|
| N1 | Nhánh đệm lặng vẫn đệm vào *trong file câu* (`pad_silence(out_path, …)`), nên các câu đó không "nhả" được độ trễ đã tích. Có muốn bỏ đệm trong file câu (kèm tăng tốc cả đoạn ít hơn) không, hay giữ nguyên? | **Đồng ý bỏ đệm (13/11) — đã sửa.** `_synthesize_with_adaptive_rate` không còn `pad_silence` vào file câu; khoảng lặng do `place_on_timeline` dựng. `run_experiment.py` V4 tính `t_final = max(độ dài file, t_orig)` cho nhất quán với V1–V3. Test: 60 passed. Cần restart `lms_ai_worker` sau khi pull. |
| N2 | Tăng tốc cả đoạn tới ×1,08 (tối đa cho phép ×1,15) có chấp nhận được về độ tự nhiên không? (MOS sẽ đo; nếu không, hạ `MAX_CHUNK_TEMPO`?) | **Giữ `MAX_CHUNK_TEMPO` = 1,15.** Thực tế đo 1,00–1,04; MOS kiểm chứng. |
| N3 | Bảng Δ của V4 sẽ xấu đi nhẹ (+20% thời gian tràn theo câu) nhưng trễ theo trục thời gian tốt hơn rõ. Bài trình bày cả hai chỉ số như vậy được không? | **Được — trình bày cả hai.** Trễ theo trục thời gian là chỉ số chính (người nghe cảm nhận); Δ theo câu báo kèm, nói rõ đánh đổi có chủ đích (khớp toàn bài + giảm ~½ lời gọi rút gọn). |
| N4 | ~~Cho phép restart `lms_ai_worker`~~ **Đã xong (12/11 16:02 UTC, Thiện tự chốt)** — xem mục 2 ở trên. Sang chỉ cần xem có muốn thêm giới hạn log trong compose và loại `NCKH/` khỏi `--reload` của `lms_ai_api` không. | **Có, làm cả hai** (Thiện sửa trên server): giới hạn log `json-file` (`max-size`, `max-file`) cho các container ai-worker trong compose; loại `NCKH/` khỏi theo dõi `--reload` của `lms_ai_api`. Ghi lại thay đổi vào report. |
| N5 | Nếu credit chưa kịp nạp trước 13/11: có chấp nhận dựng audio V2/V4 cho MOS bằng cách **tái dùng văn bản đã lưu** trong `full_r1/segments.csv` + gọi lại **Azure TTS** (không dùng Gemini), ghép bằng `place_on_timeline` không? (Không phải một lần chạy pipeline mới hoàn toàn; văn bản từ lần chạy 10/11.) | **Cho phép** nếu credit chưa kịp: dựng audio MOS từ văn bản đã lưu của `full_r1` + Azure TTS + `place_on_timeline`. Ghi rõ trong NOTES và report là văn bản từ lần chạy 10/11. Có credit kịp thì ưu tiên chạy thật. |

**Thiện sẽ làm ngay khi Sang trả lời và có credit:** kiểm tra credit (1 lần gọi 1 từ) → restart + ghi commit vào NOTES → kiểm tra Q7 → chạy `run_experiment.py` V1–V4 trên server (`post_fix_r1`, ước ~36K₫) →
lồng tiếng thật 4 bài qua web (ước ~36K₫) → lấy số liệu server → MOS → cập nhật report. Cần nạp khoảng **≥ 150K₫** (ước tính ~72–80K₫ cho phần bắt buộc, còn lại là dự phòng).

> **Đây là file report duy nhất.** Đã gộp bản đo đạc 10/11 và bản báo cáo tình hình 11/11 vào đây.
> **Cách dùng:** Sang đọc §0 → §3 (quyết định), tra §4 khi cần bằng chứng. Trả lời bằng cách **sửa trực tiếp các ô "Trả lời của Sang"**
> (hoặc nhắn Thiện). Thiện sẽ quyết định hướng đi tiếp dựa trên các câu trả lời đó.
>
> **Vị trí:** repo `urglydog/ailms-ai-worker`, nhánh **`NCKH`**, đường dẫn `NCKH/experiments/reports/REPORT_20261111_Thien.md`.
> **Audio KHÔNG nằm trong repo** (đã loại bằng `.gitignore`: `results/*/audio/`, `.cache/`, `media/`). Quyết định ở §0–§3 không cần nghe audio;
> nếu Sang muốn nghe, nhờ Thiện gửi riêng (ví dụ bản ghép V4 của `lec04`: dài 995,9 s trong khi video gốc 900 s).
> **Chưa sửa code app và chưa sửa `paper/main.tex`.** Mọi đề xuất sửa pipeline ở đây là để Sang quyết định.

## 0. Bức tranh trong 10 dòng

1. Đã có số liệu cho **4 bài giảng CNTT, 50 phút, 787 câu**, đủ V1–V4, **chỉ 1 lần chạy** (`full_r1`); đợt 1 (603 câu, 10 phút đầu mỗi bài) cho xu hướng giống nhau.
2. **Thuật toán chỉnh tốc độ đọc đúng như thiết kế ở mức từng câu:** Δ trung bình V1 → V4 = 1,649 → 0,190 s; % câu còn tràn 94,0 → 26,7.
3. **Nhưng audio sau khi ghép dài hơn video gốc và trễ dần:** V4 +1,7% đến +10,7% (+9,4 s đến +95,9 s), V2 +18% đến +34%. Mâu thuẫn với câu trong bài "mỗi đoạn có thời lượng đúng bằng L, không tích lũy độ trễ".
4. **Gốc rễ còn lại nằm ở câu rất ngắn:** 193/787 câu (24,5%) có khung < 2 s; 148 câu trong số đó vẫn chạm trần +30%, và nhóm chạm trần gây **90,3%** tổng thời gian tràn của V4. Các câu này cũng ngốn **53%** số lần gọi LLM rút gọn (§4.4).
5. **Dữ liệu chưa khớp mô tả bài:** cả 4 bài đều CNTT (không có kỹ năng mềm), chỉ có audio, giấy phép chưa xác minh.
6. **Chưa có:** số liệu server, chấm độ trung thành (L4), MOS, bản chạy lặp (L3 thất bại do hết credit Gemini).
7. **Credit Gemini hết** (HTTP 402) ngày 10/11. Ước tính ~109₫/lần gọi, ~75K₫ cho một lượt V4 50 phút.
8. **Thiện đang chờ Sang trả lời §1–§2 trước khi tốn thêm credit hoặc chạy tiếp**, vì nếu sửa pipeline thì phải đo lại trên bản đã sửa.

## 1. Ba điều Thiện cần Sang xác nhận

### Câu hỏi 1 — Pipeline hoạt động đúng chưa?

**Nhận định của Thiện:** *đúng ở phần thuật toán, chưa đúng ở phần ghép audio so với những gì bài báo mô tả.* Các điểm cụ thể:

| # | Quan sát | Bằng chứng | Mức chắc chắn |
|---|---|---|---|
| E1 | Chỉnh tốc độ đọc hoạt động như thiết kế | V4 Δ TB 0,190 s so với V1 1,649 s (§4.1) | Đo 1 lần chạy |
| E2 | Audio ghép **dài hơn bản gốc**, trễ cộng dồn | §4.2: V4 +9,4 s đến +95,9 s | Đo trên file ghép lại bằng hàm của pipeline; chưa đo `final.mp3` thật |
| E3 | Cơ chế: khoảng lặng trước mỗi câu là `seg.start − prev_end` của bản gốc (cố định), câu tràn đẩy lùi các câu sau mà không bù; cuối đoạn chỉ đệm `max(0, …)`, không cắt | [dubbing_service.py:284](../../../app/services/dubbing_service.py#L284), [:319-321](../../../app/services/dubbing_service.py#L319) | Đọc từ code, khớp số đo |
| E4 | 90,3% thời gian tràn của V4 đến từ nhóm câu chạm trần +30%; 84,6% nhóm đó là câu có khung < 2 s | §4.4 | Tính từ `segments.csv` |
| E5 | 53,3% số lần gọi LLM rút gọn (360/676) dành cho câu có khung < 2 s; 51,8% (350/676) dành cho câu **cuối cùng vẫn chạm trần** → tốn credit mà không giải quyết được | §4.4 | Tính từ `segments.csv` |
| E6 | ASR trả mốc vượt hết audio (`lec03` câu cuối *"Thank you."*, 709,44 → 739,42 s, audio dài 718,0 s) → đoạn cuối bị đệm thêm ~21 s | §4.5 | Đã đối chiếu `asr_cache.json` |
| E7 | Provider Gemini không phân biệt lỗi 402 (hết credit) với 5xx; log chỉ báo "network error"/"cooldown" | Log `full_r2.log` | Quan sát từ log |

Chưa biết: pipeline **trên server** có bị giống vậy không (chưa lấy số liệu S1; chưa đo `final.mp3` thật). Bản chạy trên server có thể đã khác code của máy đo (S5).

**Các câu hỏi con:**

**1a. Ghép audio (E2–E3):** mô phỏng xếp câu theo **mốc tuyệt đối** (`onset = max(mốc gốc, thời điểm câu trước kết thúc)`, giữ nguyên câu dịch và giọng đọc) cho thấy trễ tối đa của V4 giảm từ 96 s xuống ~18 s ở `lec04` (§4.3). Sang chọn:
- **A.** Sửa phần ghép (và tuỳ chọn: tăng tốc nhẹ cả đoạn nếu cuối đoạn vẫn dài hơn khung).
- **B.** Giữ nguyên code, sửa bài cho đúng cơ chế và nêu trễ cộng dồn như hạn chế.
- **C.** Khác.

> **Trả lời của Sang:** ☐ A ☐ B ☐ C: ______________________  Ghi chú: ______________________

**1b. Câu rất ngắn (E4–E5):** ASR cắt thành nhiều mảnh rất ngắn (24,5% câu có khung < 2 s, ví dụ *"Thought Cafe."*, *"Thank you."*); bản dịch tiếng Việt không vừa dù +30% và vài lần rút gọn. Hướng có thể thử (chưa làm): (i) gộp mảnh < ~2 s với câu liền kề trước khi dịch; (ii) bỏ bước rút gọn LLM cho khung quá ngắn, mượn khoảng lặng kế bên; (iii) để nguyên và mô tả đây là giới hạn. Sang đánh giá?

> **Trả lời của Sang:** ☐ (i) ☐ (ii) ☐ (iii) ☐ Khác: ______________________  Ghi chú: ______________________

**1c. Mốc ASR (E6):** có nên giới hạn `start/end` của câu trong [0, thời lượng audio] và trong biên đoạn, và bỏ câu có `start` ≥ thời lượng không?

> **Trả lời của Sang:** ☐ Có ☐ Không ☐ Khác: ______________________

**1d. Gemini (E7 và chi phí):** (i) có muốn log thêm token suy nghĩ (`thoughtsTokenCount`) và phân biệt lỗi 402 không? (ii) code không đặt `thinkingBudget`/`maxOutputTokens`; nếu nghi token suy nghĩ ẩn là nguyên nhân đơn giá cao, có muốn thử hạ ngân sách suy nghĩ cho lời gọi rút gọn không (đổi chất lượng câu rút gọn → phải đo lại)?

> **Trả lời của Sang:** ______________________

**1e. Phiên bản code và model trên server (S5):** server đang chạy commit nào, `GEMINI_MODEL`, `CHUNK_MINUTES`? Máy đo đang dùng `11378e5` + `gemini-3.5-flash`.

> **Trả lời của Sang:** ______________________

### Câu hỏi 2 — Các luận điểm trong bài nghiên cứu đúng chưa?

Đối chiếu từng khẳng định trong `paper/main.tex` với bằng chứng hiện có:

| # | Khẳng định trong bài | Bằng chứng hiện có | Kết luận của Thiện | Đề xuất |
|---|---|---|---|---|
| T1 | "âm thanh lồng tiếng **luôn khớp với hình ảnh**" (Tóm tắt) | Audio ghép dài hơn gốc +1,7% đến +10,7% (V4); câu trễ tới 96 s | **Chưa đúng** với code hiện tại | Sửa code (A) hoặc sửa câu |
| T2 | "mỗi đoạn … thời lượng **đúng bằng L** … **không tích lũy độ trễ giữa các đoạn**" (Mục 3.6) | Không đoạn nào ghép đúng bằng khung (vd `lec04` V4: 600 → 654,87 s, 300 → 341,01 s) | **Sai** theo số đo | Sửa code (A) hoặc sửa câu |
| T3 | Dịch hai pha cải thiện độ khớp | Δ V1 → V2: 1,649 → 1,093 (`full_r1`), 1,679 → 0,989 (đợt 1) | **Đúng**, nhưng mới 1 lần chạy mỗi đợt | Giữ; thêm độ dao động nếu có |
| T4 | Tăng tốc ≤ 30% + rút gọn giúp khớp mà vẫn tự nhiên | Δ V3 0,392; V4 0,190 | Phần "khớp" **đúng**; phần "**tự nhiên**" **chưa kiểm chứng** (chưa có MOS) | Cần MOS hoặc bỏ/ghi hạn chế |
| T5 | Rút gọn "giữ ý chính" | Chưa chấm L4; ví dụ *"Thought Cafe."* → *"Tư duy"* | **Chưa kiểm chứng** | Chấm 50 câu (L4) |
| T6 | Giới hạn M = 2 lần rút gọn là đủ | 350 lần gọi (51,8%) dành cho câu cuối cùng vẫn chạm trần | M = 2 **không giải quyết** được câu ngắn; chỉ tốn credit | Xem 1b |
| T7 | Thực nghiệm trên video "CNTT **và kỹ năng mềm**" | 4 bài đều CNTT | **Chưa đúng** | Thêm 2 bài kỹ năng mềm hoặc sửa mô tả |
| T8 | Chia đoạn 10 phút cho phản hồi sớm | Chưa có số server (`first_chunk_sec`) | **Chưa kiểm chứng** | S1 |
| T9 | Tái sử dụng bản ký âm/bản lồng tiếng giảm chi phí | Chưa có số server (reuse) | **Chưa kiểm chứng** | S3 |
| T10 | Không cần huấn luyện mô hình, điều phối dịch vụ có sẵn | Đúng theo code | **Đúng** | Giữ |

Các câu T1–T2, T4–T5, T7–T9 cần quyết định về cách xử lý (sửa code, sửa câu, hay bổ sung số liệu).

> **Trả lời của Sang** (ghi theo số T): ______________________________________________

### Câu hỏi 3 — Các đề xuất của Thiện có ổn không?

| # | Đề xuất | Lý do | Chi phí API ước tính | Sang ok? |
|---|---|---|---|---|
| P1 | Thêm chỉ số **trễ mốc câu / tổng thời lượng so với gốc** vào mục Độ đo | Δ theo câu không bắt được trễ cộng dồn | 0 | ☐ ok ☐ không ☐ sửa |
| P2 | Chọn A hoặc B ở 1a và **chốt một commit** để đo | Hướng dẫn 9.2 yêu cầu cố định cấu hình; sửa code sau khi đo thì phải đo lại | 0 | ☐ ok ☐ không ☐ sửa |
| P3 | Xử lý câu ngắn (1b) | Giải quyết 90% độ tràn còn lại và gần nửa lượng gọi LLM rút gọn | Có thể **giảm** chi phí | ☐ ok ☐ không ☐ sửa |
| P4 | Thêm **2 video kỹ năng mềm** (mp4), giữ `lec02`, `lec04` làm 2 bài CNTT; chạy script V1–V4 cho 2 bài mới | Khớp mô tả bài; giữ liên tục với số liệu cũ | ~35–40K₫ | ☐ ok ☐ không ☐ sửa |
| P5 | Upload 4 mp4 vào **khoá học tạm**, lồng tiếng thật sang `vi-VN` **1 lần** (S4) | Có số vận hành thật, bài có video để MOS | ~75K₫ | ☐ ok ☐ không ☐ sửa |
| P6 | **Bỏ L3 chạy riêng**; dùng lần lồng tiếng web của `lec02`, `lec04` làm lần V4 thứ hai (so tổng thể: tỷ lệ rút gọn, tốc độ đọc, tổng thời lượng) | Tiết kiệm ~75–150K₫. Không so được Δ từng câu | 0 | ☐ ok ☐ không ☐ sửa |
| P7 | L4: Sang và Thiện chấm độc lập 50 câu (`results/full_r1/fidelity_sample.csv`); MOS nếu kịp | Cần cho T4, T5 | 0 | ☐ ok ☐ không ☐ sửa |
| P8 | Lấy số liệu server (S1–S3, S5) bằng SQL chỉ đọc; Thiện tự nhập mật khẩu DB | Cần cho T8, T9 | 0 | ☐ ok ☐ không ☐ sửa |

> **Trả lời / ghi chú của Sang:** ______________________________________________

## 2. Các quyết định về dữ liệu, quyền và chi phí

| # | Câu hỏi | Trả lời của Sang |
|---|---|---|
| Q4 | **Lồng tiếng thật trên hệ thống đang chạy (S4):** cho phép không? Dùng khoá học tạm của `instructor@lms.local` hay tài khoản khác? Xong có dọn không (Thiện không tự xoá dữ liệu DB)? | |
| Q5 | **Video kỹ năng mềm:** Thiện tìm hay Sang đã có sẵn? Có đồng ý đổi mô tả bài thành "lĩnh vực CNTT" nếu không kịp thêm? | |
| Q6 | **Giấy phép** 4 bài (3 bài Crash Course + Stanford CS229): ai xác minh? Có cần xin phép khi dùng trong bài? | |
| Q7 | **Credit Gemini** đã hết: Sang kiểm tra giúp các tính năng AI thật (lồng tiếng, trợ lý…) có đang lỗi không và có dùng chung key/dự án không? Ai nạp (dự kiến cần ~150K cho phần tối thiểu, ~300K nếu làm đủ)? | |
| Q8 | **Job nào trên server là test/lỗi cần loại khỏi S1?** Các bài B1, B2 của khoá Unity và Agent là link YouTube hay file upload; ngôn ngữ gốc là gì? | |
| Q9 | **Máy đo dùng chung với hệ thống thật** (2 vCPU, 3,7 GiB RAM, còn ~1 GiB): có nên chạy các đợt sau ở máy khác? Số "giây xử lý trên phút video" ở máy này không dùng làm số liệu vận hành. | |
| Q10 | **Nơi push và merge:** Thiện đang push lên nhánh `NCKH`; khi nào merge vào `develop`? | |

## 3. Thiện sẽ làm gì tiếp theo, tuỳ câu trả lời

| Nếu Sang trả lời | Thiện (cùng Claude Code) sẽ làm | Chi phí API |
|---|---|---|
| 1a = **A** | Chờ Sang sửa và chốt commit → ghép lại các file câu đã lưu bằng cách mới (không gọi API), chạy `check_full_length.py` để có số thật → chạy P4, P5 trên bản đã sửa | ~110–115K₫ |
| 1a = **B** | Giữ commit hiện tại (`11378e5`) → chạy P4, P5 ngay; ghi trễ cộng dồn như phát hiện/hạn chế; không đo lại | ~110–115K₫ |
| 1b = (i) hoặc (ii) | Sang sửa → chạy lại V4 trên 4 bài để có Δ mới (chi phí nhiều khả năng **thấp hơn** 75K₫ vì bớt lời gọi rút gọn) | ≤ ~75K₫ |
| Q4 = không cho | Chỉ dùng số liệu script (local); ghi rõ thiếu số liệu server trong hạn chế | ~35–40K₫ (P4) |
| Q5 = đổi mô tả | Bỏ P4; bài ghi "lĩnh vực CNTT"; 4 bài hiện có đủ (cần mp4 nếu muốn P5/MOS) | ~75K₫ (P5) |
| Q7 chưa nạp | Dừng mọi thứ gọi Gemini; chỉ làm L4, S1–S3 (không tốn API) | 0 |

Mốc thời gian đề xuất (hạn nộp **15/11**): 11/11 Sang trả lời §1–§2 → 12/11 sửa/chạy → 13/11 lấy số server, chấm L4 → 14/11 cập nhật report, Sang điền `main.tex` → 15/11 nộp. Mỗi việc cần Sang đã ghi ở §1–§2.

## 4. Bằng chứng chi tiết

### 4.1. So sánh V1–V4

| Phương án | Δ TB (s) | Δ trung vị | Δ p95 | % còn tràn | % R>1,3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|
| **`full_r1`** (787 câu, toàn bài, n = 1 lần chạy) | | | | | | | |
| V1 một pha | 1,649 | 1,544 | 3,46 | 94,0 | 75,6 | 7 | 787 |
| V2 hai pha | 1,093 | 1,024 | 2,632 | 84,2 | 55,8 | 14 | 787 |
| V3 hai pha + tăng tốc | 0,392 | 0,144 | 1,328 | 54,9 | 25,3 | 14 | 677 |
| V4 đề xuất | 0,190 | 0,016 | 0,916 | 26,7 | 17,0 | 690 | 2097 |
| **Đợt 1 `20261109_042122`** (603 câu, chỉ 10 phút đầu mỗi bài, n = 1) | | | | | | | |
| V1 | 1,679 | 1,556 | 3,46 | 94,2 | 75,3 | 4 | 603 |
| V2 | 0,989 | 0,908 | 2,512 | 82,9 | 48,3 | 8 | 603 |
| V3 | 0,318 | 0,044 | 1,128 | 48,1 | 18,6 | 8 | 504 |
| V4 | 0,157 | 0,016 | 0,908 | 23,5 | 13,8 | 444 | 1507 |

Phân bố nhánh V4 (`full_r1`): rút gọn 33,5%, tăng tốc 29,6%, chạm trần 22,2%, đệm lặng 14,6%. R mặc định sau pha 2: R ≤ 1,0: 14,0%; 1,0–1,3: 30,2%; > 1,3: 55,8%.
Khác biệt nhỏ giữa hai đợt chưa quy được cho nguyên nhân nào (LLM không tất định, tập câu khác); cần chạy lặp mới biết độ dao động. Nguồn: `results/full_r1/summary.json`, `results/20261109_042122/summary.json`.

### 4.2. Audio ghép thật dài hơn bản gốc (`results/full_r1/check_full_length.md`)

| Video | Phương án | Gốc (s) | Sau ghép (s) | Chênh | Trễ mốc câu TB / p95 / max (s) | % câu trễ > 1 s |
|---|---|---|---|---|---|---|
| lec01 | V2 | 566,0 | 695,14 | +22,8% | 66,7 / 118,7 / 127,7 | 98,5 |
| lec01 | V4 | 566,0 | 575,41 | +1,7% | 3,1 / 6,8 / 8,0 | 70,2 |
| lec02 | V2 | 815,1 | 1093,03 | +34,1% | 130,8 / 261,4 / 277,1 | 98,4 |
| lec02 | V4 | 815,1 | 833,39 | +2,2% | 8,1 / 15,8 / 17,5 | 98,4 |
| lec03 | V2 | 718,0 | 898,28 | +25,1% | 91,5 / 169,3 / 186,1 | 98,9 |
| lec03 | V4 | 718,0 | 761,50 | +6,1% | 7,8 / 18,0 / 22,1 | 89,5 |
| lec04 | V2 | 900,0 | 1063,54 | +18,2% | 72,1 / 142,8 / 164,0 | 92,4 |
| lec04 | V4 | 900,0 | 995,89 | +10,7% | 43,1 / 82,2 / 95,9 | 99,0 |

Cách đo: ghép lại audio đúng như `dubbing_service._process_chunk` (khoảng lặng = `start − prev_end` của bản gốc, đệm cuối đoạn nếu thiếu, nối đoạn bằng `audio_utils.concat_files`), đo bằng `audio_utils.measure_duration_sec`. **Giới hạn:** dùng file câu của thí nghiệm, chưa phải `final.mp3` của server. Không kiểm V3 (nhánh `pad` của V3 không lưu file riêng) và V1.
Độ trễ tăng theo độ dài video: bài 9,4 phút lệch 9,4 s, bài 15 phút lệch 95,9 s (V4); ở video ngắn, vài giây trễ khó nhận ra bằng tai. Chưa đo ở độ dài lớn (bài nêu tối đa 180 phút).
Ước lượng độc lập từ CSV (`drift_analysis.py`) khớp số đo, trừ `lec03` do E6.

### 4.3. Mô phỏng xếp câu theo mốc tuyệt đối (ước lượng, không phải audio thật; `results/full_r1/simulate_resync.md`)

| Video (V4) | Trễ max hiện tại (đo thật) | Trễ max sau mô phỏng | Trễ TB hiện tại → mô phỏng | % câu trễ > 2 s hiện tại → mô phỏng |
|---|---|---|---|---|
| lec01 | 8,0 s | 2,7 s | 3,1 → 0,7 s | 61,1 → 0,8 |
| lec02 | 17,5 s | 10,4 s | 8,1 → 3,0 s | 93,5 → 50,3 |
| lec03 | 22,1 s | 5,6 s | 7,8 → 1,5 s | 85,1 → 29,8 |
| lec04 | 95,9 s | 18,5 s | 43,1 → 3,2 s | 94,1 → 40,7 |

Cải thiện lớn nhưng **không về 0**: đoạn dày lời không đủ khoảng lặng để bù. Với V2 (không rút gọn) mô phỏng vẫn trễ max 79–265 s, nghĩa là xếp theo mốc tuyệt đối **không đủ nếu thiếu rút gọn/tăng tốc của V4**. Vì file câu đã lưu (`--keep-audio`), ghép lại theo cách mới **không tốn API**.

### 4.4. Câu ngắn là nguồn của phần trễ còn lại (V4, `full_r1/segments.csv`)

| Chỉ số | Giá trị |
|---|---|
| Câu có khung `t_orig` < 2 s | 193 / 787 (24,5%); trung vị khung của nhóm chạm trần = 1,16 s (toàn bộ câu: 3,78 s) |
| Câu chạm trần +30% (`capped`) | 175; trong đó 148 (84,6%) có khung < 2 s |
| Tổng thời gian tràn của V4 | 147,5 s; do nhóm `capped` gây ra: 133,3 s (**90,3%**); riêng nhóm khung < 2 s: 121,2 s |
| Lời gọi LLM rút gọn của V4 | 676 lần; 360 (53,3%) dành cho câu khung < 2 s; 350 (51,8%) dành cho câu **kết thúc ở trạng thái `capped`** (đã rút gọn 2 lần vẫn tràn) |

Suy ra: gần một nửa chi phí Gemini của V4 chi cho các lần rút gọn không đưa được câu về đúng khung. Đây là cơ sở của đề xuất P3/1b (chưa thử).

### 4.5. ASR cho mốc vượt hết audio (`lec03`)
Câu cuối seq 181 *"Thank you."*: mốc 709,44 → 739,42 s, `t_orig` = 29,98 s (cột `t_orig` của `segments.csv`; mốc gốc trong `.cache/lec03/asr_cache.json`, không commit), trong khi audio dài 718,0 s. Pipeline không giới hạn mốc theo thời lượng audio nên đoạn cuối bị đệm thêm ~21 s. Bỏ câu này, chênh của `lec03` V4 ≈ 22 s, khớp ước lượng 22,09 s từ CSV.

### 4.6. Dữ liệu đã dùng

| id | Tên bài | URL | Giấy phép | Nhãn manifest | Nội dung thực | Thời lượng | Số câu |
|---|---|---|---|---|---|---|---|
| lec01 | Crash Course CS #10: Early Programming | https://www.youtube.com/watch?v=nwDq4adJwzM | chưa xác minh | CNTT | CNTT | 566,0 s | 131 |
| lec02 | Crash Course CS #18: Operating Systems | https://www.youtube.com/watch?v=26QPDBe-NB8 | chưa xác minh | CNTT | CNTT | 815,1 s | 185 |
| lec03 | Crash Course CS #29: The Internet | https://www.youtube.com/watch?v=AEaKrq3SpW8 | chưa xác minh | **KyNangMem** | **CNTT** | 718,0 s | 181 |
| lec04 | Stanford CS229, Lecture 1 (15 phút đầu) | https://www.youtube.com/watch?v=UzxYlbK2c7E | chưa xác minh | **KyNangMem** | **CNTT** | 900,0 s | 290 |

Tổng 50,0 phút, 787 câu, ngôn ngữ nguồn English cho cả 4 bài. Đầu vào là **audio mp3** tách từ video (lệnh tách ban đầu chưa ghi lại — Thiện bổ sung). Nhãn `category` sai ở `lec03`, `lec04` chưa sửa vì sẽ làm `run_meta` không khớp với run đã chạy.

### 4.7. Vận hành và chi phí
- **Credit Gemini hết** lúc 20:52 UTC 10/11. Chẩn đoán: mạng bình thường; một lần gọi thử trả `HTTP 402 RESOURCE_EXHAUSTED — "Your prepayment credits are depleted"`. Key nằm trong `lms_ai_worker` (container cũng phục vụ hệ thống thật); chưa kiểm tra tác động lên hệ thống thật.
- **Ước tính chi phí** (billing AI Studio, tổng ₫133K từ 1–11/11; cột 10/11 = ₫86,08K): `full_r1` 690 lần gọi + `full_r2` (chỉ `lec01`) 101 + 1 lần gọi thử = ~792 lần ≈ **109₫/lần**; đợt 1 (444 lần gọi) khoảng 100₫/lần (đọc từ biểu đồ). Một lượt V4 50 phút ≈ **75K₫**; V2 ~14 lần gọi nên không đáng kể. Nguyên nhân đơn giá cao **chưa xác định** (nghi token suy nghĩ ẩn; chưa kiểm chứng).
- **L3 thất bại:** `full_r2` chỉ có `lec01`, `full_r3` không dữ liệu — giữ lại kèm `NOTES.md` để minh bạch.

## Phụ lục A — Đã làm / chưa làm theo kế hoạch đợt 2 (mục 9 của `HUONG_DAN_NHOM.md`)

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| L1 nguồn dữ liệu | Một phần | Có link; thiếu giấy phép; không có bài kỹ năng mềm |
| L2 toàn bộ độ dài | **Xong** (`full_r1`) | Lệnh: `docker exec --user 1000:1001 lms_ai_worker python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r1 --keep-audio`; không lỗi; ASR gọi lại Groq cho `lec02`–`lec04` |
| Kiểm tra ghép audio thật | **Xong** (V2, V4) | `check_full_length.py` |
| L3 lặp lại | **Thất bại** | Hết credit Gemini (402), xem §4.7 |
| L4 độ trung thành | Mới tạo mẫu | 50 câu (seed 42) từ pool 439 câu rút gọn của V4; chờ Sang, Thiện chấm |
| L5 MOS | Không làm | Cần video gốc và 8–15 người nghe |
| L6 cấu hình máy | Xong | Bảng bên dưới; mạng chưa đo |
| S1–S5 server | Không làm | Chờ Sang cho phép và cung cấp thông tin |

**Môi trường (máy đo, dùng chung với hệ thống thật):** host `ubuntu-4gb-fsn1-2`; Ubuntu 22.04.5, kernel 5.15.0-198; 2 vCPU Intel Xeon Skylake; RAM 3,7 GiB; Docker 29.9.2; container `lms_ai_worker` chạy uid 1000:1001. Commit `11378e5` (cây làm việc chỉ khác `videos.json` — trường `note` — và các script mới).
Tham số: `chunk_minutes=10`, `r_min=1,0`, `r_max=1,3`, `max_tts_rate=+30%`, `max_resummarize_attempts=2`, `min_speech_ratio=0,1`; ASR `whisper-large-v3-turbo`; LLM `gemini-3.5-flash`; TTS Azure Neural `vi-VN-HoaiMyNeural`/`vi-VN-NamMinhNeural`. `full_r1`: 10/11 17:20:18 – 20:11:02 UTC.

**Sự cố và thay đổi trong quá trình thực hiện:** `git pull` lỗi quyền vì `results/` thuộc root (đã `chown` lại); `docker builder prune -f` giải phóng 2,11 GB (không đụng volume, image, DB); sửa trường `note` của `videos.json` trong lúc chạy (không đổi tham số); `full_r2`/`full_r3` hỏng do hết credit; số "giây xử lý trên phút video" ở local không đại diện cho server.

## Phụ lục B — File, và cách kiểm tra lại các con số

```bash
cd /var/lms/ai-worker            # hoặc thư mục gốc repo ai-worker
python NCKH/experiments/analyze.py NCKH/experiments/results/full_r1          # §4.1
python NCKH/experiments/drift_analysis.py NCKH/experiments/results/full_r1   # ước lượng trễ từ CSV
python NCKH/experiments/simulate_resync.py NCKH/experiments/results/full_r1 --variants V2,V4   # §4.3 (không gọi API)
# §4.2 cần audio/ của run (không commit), chạy trong container ai-worker:
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/check_full_length.py NCKH/experiments/results/full_r1 --variants V2,V4
```
§4.4 tính trực tiếp từ `results/full_r1/segments.csv` (V4): nhóm `branch == "capped"`, cột `t_orig`, `t_final`, `n_resummarize`.

File trong repo (`NCKH/experiments/`): script `drift_analysis.py`, `check_full_length.py`, `simulate_resync.py`, `aggregate_runs.py`, `sample_fidelity.py`; kết quả `results/full_r1/` (kể cả `NOTES.md`, `fidelity_sample.csv`, `fidelity_scores.csv`), `results/full_r2/`, `results/full_r3/` (run lỗi, có `NOTES.md`); đợt 1 `results/20261109_042122/`.
`audio/`, `.cache/`, `media/` không nằm trong repo.
