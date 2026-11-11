# REPORT – Thiện – 11/11/2026 — Tình hình thực nghiệm và các câu hỏi gửi Sang

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
