# Cải tiến tốc độ xử lý và chi phí API của pipeline lồng tiếng (15/11/2026)

## 1. Mục tiêu và kết quả

**Mục tiêu:** lồng tiếng một video 10 phút trong khoảng 1–2 phút và giảm số lời gọi API có tính tiền.

Tất cả các job đo trên máy local, worker chạy Docker, một chunk 10 phút.

| Chỉ số | Trước (job 29) | Sau (job 32) |
|---|---|---|
| Bài | 2631, khoảng 6 phút, 90 câu, sang tiếng Việt | 2633, khoảng 5 phút, 74 câu, sang tiếng Hàn, bài chưa từng lồng tiếng |
| Thời gian xử lý chunk | 212,9 s | **60,5 s** |
| Thời gian cả job | 222 s (khoảng 37 s cho 1 phút video) | **87 s** (khoảng 17 s cho 1 phút video) |
| Dịch | 61,1 s | 7,8 s |
| Tạo giọng (gồm rút gọn) | 92,2 s | 11,8 s |
| Ghép (gồm embedding) | 47,0 s | 14,4 s |
| Azure TTS: lời gọi trên mỗi câu | khoảng 1,48 (133 cho 90 câu) | **khoảng 1,03 (76 cho 74 câu)** |
| Gemini generateContent | 4 | 3 |
| Gemini embedding | 90 lời gọi (mỗi câu 1 lời gọi) | **1 lời gọi theo lô** |

Bản gốc trước mọi cải tiến (số đo trong NCKH) mất khoảng 110 s cho mỗi phút video và gọi TTS khoảng **2,7 lần cho mỗi câu**.

**Lưu ý khi so sánh:**
- Các job dịch sang ngôn ngữ khác nhau, nên đây là so sánh tương đối.
- Bước tải lên của job 32 chậm bất thường (22 s; các job khác khoảng 9 s).

## 2. Các cải tiến

### 2.1. Tạo giọng song song (`dubbing_service._synthesize_segments`)
- **Trước:** tạo giọng tuần tự từng câu.
- **Sau:** tất cả câu trong chunk được tạo giọng cùng lúc, giới hạn bằng `asyncio.Semaphore(TTS_CONCURRENCY=8)`.
- **Lý do:** Azure Speech gói S0 cho khoảng 100 request mỗi 10 s. Thời gian chủ yếu là chờ mạng, nên chạy song song gần như rút được toàn bộ phần chờ.

### 2.2. Tăng tốc cục bộ bằng FFmpeg `atempo` thay cho đọc lại (`audio_utils.change_tempo`)
- **Trước:** câu dài hơn khung một chút thì gọi lại Azure với `rate` lớn hơn. Mỗi lần như vậy tốn thêm 1 request và trả tiền ký tự thêm một lần.
- **Sau:** đã có file và đã đo độ dài nên tăng tốc ngay trên máy, giữ cao độ giọng, trần ×1,3 (đúng mức +30% của BR-DUB-03).
- **Lý do:** không tốn request, không tốn ký tự. Hai cách cho chất lượng tương đương ở mức ≤ ×1,3.

### 2.3. Rút gọn theo lô (`translation.resummarize_batch`)
- **Trước:** mỗi câu quá dài gọi Gemini rút gọn riêng.
- **Sau:** mỗi vòng chỉ 1 lời gọi cho tất cả câu có R > 1,3 (và khung ≥ `MIN_RESUMMARIZE_FRAME_SEC`). Mỗi câu kèm `max_chars` tính từ tốc độ đọc thật của chính câu đó. Tối đa `MAX_RESUMMARIZE_ATTEMPTS` vòng.
- **Lý do:** bớt hàng chục lời gọi Gemini mỗi bài. Nếu lời gọi lỗi thì chuyển sang tăng tốc, job không bị hỏng.

### 2.4. Tắt "suy nghĩ" của Gemini khi dịch (`DUBBING_THINKING_LEVEL=minimal`)
- **Trước:** dùng mặc định của model, nên model chạy suy nghĩ ẩn. Mỗi lời gọi mất 25–45 s, và token suy nghĩ cũng bị tính tiền.
- **Sau:** `generationConfig.thinkingConfig.thinkingLevel = "minimal"`. Theo docs của Google, đây là mức gần như tắt, có độ trễ thấp nhất.
- **Số đo:** cùng một câu, 3,8 s xuống **0,8 s**. Trong job thật, bước dịch giảm từ 61 s xuống còn 8–19 s.
- **Lý do:** dịch và biên tập lời thoại không cần suy luận. Gemini 3.x không có mức "off", và `minimal` là mức thấp nhất.

### 2.5. Gộp dịch và biên tập thành 1 lời gọi (`translation.translate_batch`)
- **Trước:** 2 lời gọi cho mỗi chunk: dịch sát nghĩa, rồi biên tập cho tự nhiên và vừa thời lượng. Bản dịch sát nghĩa chỉ dùng làm dự phòng.
- **Sau:** 1 lời gọi làm cả dịch đúng nghĩa và viết thành lời nói tự nhiên, kèm `budget_sec` và (nếu có) `max_chars` cho từng câu. "3 bước" của pipeline dịch là 3 giai đoạn nghiệp vụ, không bắt buộc là 3 request.
- **Lý do:** bớt 1 lời gọi và một nửa token dịch. Giới hạn ký tự đặt ngay từ đầu giúp ít câu phải rút gọn về sau.

### 2.6. Giới hạn ký tự theo tốc độ đọc đo được của giọng (Redis `dubbing:tts_cps:{voice}`)
- **Trước:** câu dịch không có giới hạn độ dài, nên phải đọc thử xong mới biết câu quá dài, rồi rút gọn và đọc lại. Job 31 (tiếng Hàn, lần đầu) phải đọc lại 44 trên 90 câu.
- **Sau:**
  - Sau lượt tạo giọng đầu tiên, worker đo số ký tự mỗi giây thật của giọng đó và lưu vào Redis. Giá trị được làm mượt theo tỉ lệ 0,7 cũ và 0,3 mới.
  - Các job sau dùng giọng đó sẽ dịch kèm `max_chars = cps × thời lượng câu × 1,15`, nhắm R ≈ 1,15. Phần dư nhỏ được tăng tốc cục bộ.
- **Kết quả:** job 32 (tiếng Hàn, đã có số đo) chỉ đọc lại **2 trên 74 câu** (3%, trước là 49%). Số câu chạm trần ×1,3 giảm từ 24% xuống 15%.
- **Lý do:**
  - Không cần bảng tốc độ cho từng ngôn ngữ, nên đúng BR-DUB-07 (không hardcode danh sách ngôn ngữ).
  - Số đo dùng chung cho mọi người dùng và mọi bài học.
  - Lần đầu dùng một giọng thì chạy như cũ. Nếu Redis mất dữ liệu thì hệ thống tự đo lại.

### 2.7. Embedding theo lô (`gemini.embed_contents` → `batchEmbedContents`)
- **Trước:** `tutor_indexing` gọi `embedContent` cho từng câu, tức 90 lời gọi tuần tự (khoảng 30 s).
- **Sau:** 1 request cho tối đa 100 câu, dùng chung key pool và chính sách thử lại với `embed_content`.
- **Kiểm chứng:** vector nhận được trùng khớp với cách gọi từng câu (cos = 1,0).

### 2.8. Chunk chạy lại không trả tiền 2 lần
- **Trước:** chunk lỗi rồi chạy lại (BR-CHUNK-04) thì phải dịch lại và đọc lại toàn bộ. Job 30 tốn thêm 90 lời gọi Azure và 2 lời gọi Gemini vì lý do này.
- **Sau:**
  - Bản dịch được lưu ở `chunk_{i}_translated.json`.
  - Mỗi file giọng có file đi kèm `*.mp3.json` ghi văn bản và thời lượng. Câu nào có file hợp lệ cho đúng văn bản đó thì dùng lại.
  - File đi kèm bị xóa trước khi file giọng bị tăng tốc, để không bao giờ dùng lại một file đã đổi tốc độ.
- File trung gian vẫn được dọn theo BR-STORAGE-01 khi job kết thúc.

### 2.9. Log TIMING cho từng chunk
Mỗi chunk ghi một dòng
`TIMING job=… chunk=… cau=… asr=… dich=… tts=… ghep=… upload=… tong=…`
để đo và so sánh. Mọi số liệu trong tài liệu này lấy từ dòng log này.

## 3. Lỗi phát hiện trong lúc đo và đã sửa

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Chunk hỏng với "Decoding failed … ffmpeg 183" (job 30) | Gemini bỏ sót 2 câu cuối, Azure nhận văn bản rỗng và trả về file 0 byte | `translate_batch` dịch lại riêng các câu thiếu trong 1 lời gọi; vẫn thiếu thì giữ câu gốc. Không bao giờ còn câu rỗng. |
| "Lock … is bound to a different event loop" ở job thứ 2 trong cùng tiến trình worker (job 32) | `_token_lock` của Azure TTS được tạo ở cấp module. Mỗi task Celery chạy `asyncio.run` với một event loop mới, và từ khi tạo giọng chạy song song thì khóa bị tranh chấp | Mỗi event loop có khóa riêng (`azure_tts._token_lock()`) |

## 4. Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `TTS_CONCURRENCY` | 8 | Số câu tạo giọng cùng lúc (đặt 1 để quay về tuần tự) |
| `TEMPO_CONCURRENCY` | 2 | Số tiến trình FFmpeg `atempo` chạy cùng lúc |
| `DUBBING_THINKING_LEVEL` | rỗng (mặc định của model) | **Nên đặt `minimal`** trên mọi môi trường |
| `MAX_RESUMMARIZE_ATTEMPTS` | 2 | Số vòng rút gọn tối đa |
| `MIN_RESUMMARIZE_FRAME_SEC` | 2.0 | Câu có khung ngắn hơn ngưỡng này không gọi LLM rút gọn |

**Chọn model** (theo trang pricing của Google AI Studio, 15/11/2026):
- Hiện đang dùng `gemini-3.5-flash`, chạy tốt ở mức `minimal`.
- Nếu muốn rẻ hơn nữa có thể thử `gemini-3.1-flash-lite` hoặc `gemini-3.5-flash-lite`. Cả hai đều mặc định suy nghĩ ở mức `minimal` và rẻ hơn dòng Flash. Cần nghe thử chất lượng dịch trước khi đổi.
- `gemini-2.5-flash` đã bị deprecate và sẽ tự chuyển sang `gemini-3.5-flash-lite` từ 01/12/2026.

## 5. Kiểm thử

- `tests/test_adaptive_rate.py`:
  - vừa khung;
  - tăng tốc cục bộ;
  - rút gọn theo lô;
  - giới hạn số vòng rút gọn;
  - câu có khung ngắn;
  - lời gọi rút gọn bị lỗi;
  - chạy song song đúng giới hạn;
  - dùng lại file giọng khi chunk chạy lại;
  - không dùng lại file đã tăng tốc.
- `tests/test_translation.py`: dịch đúng 1 lời gọi cho mỗi chunk, prompt có `max_chars`.
- `tests/test_translate_missing.py`: câu bị thiếu được dịch lại; vẫn thiếu thì giữ câu gốc.
- `tests/test_tutor_indexing.py`: embedding đúng 1 lời gọi theo lô.
- `tests/test_azure_token_lock.py`: khóa token chạy đúng qua nhiều event loop. Test này hỏng với code cũ.
- `tests/test_timeline.py`: `change_tempo` rút ngắn file tại chỗ.

Kết quả: **68 passed, 6 skipped**, chạy trong container `lms_ai_worker`.

## 6. Việc còn lại

- **Nhạc nền (M2):** tách giọng và nhạc bằng Demucs, giữ lại nhạc nền trong các đoạn không có lời. Người dùng đã chọn làm phần này sau.
- **Câu chạm trần ×1,3:** vẫn còn khoảng 15% với tiếng Hàn. Có thể hạ hệ số `_TARGET_R` hoặc thêm một vòng rút gọn nếu nghe thấy câu bị nhanh.
- **Script NCKH:** `_synthesize_with_adaptive_rate` vẫn giữ chữ ký cũ cho script NCKH, nhưng số liệu trong bài báo được đo bằng bản cũ.
