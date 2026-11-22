# So sánh 2 cách ghép câu thành chunk: pydub (cũ) và 1 lệnh FFmpeg (mới), 22/11/2026

Nhánh: `perf/timeline-ffmpeg` (tách từ `feat/dubbing`). Tiếp theo [CaiTien_TocDo_Dubbing.md](CaiTien_TocDo_Dubbing.md) và [CaiTien_NhacNen_Dubbing.md](CaiTien_NhacNen_Dubbing.md).

## 1. Bước "ghép" làm gì

Sau khi tạo giọng, mỗi câu là một file MP3. Bước ghép (`audio_utils.place_on_timeline`) dựng thành **một file audio cho cả chunk** theo quy tắc BR-CHUNK-05:
1. Đặt mỗi câu tại **mốc tuyệt đối** của nó (`plan_onsets`). Câu sau không bao giờ chồng lên câu trước; câu bị lùi sẽ quay về đúng mốc ngay khi gặp khoảng lặng đủ dài.
2. Nếu cả chunk dài hơn khung thì **tăng tốc cả đoạn** (FFmpeg `atempo`, tối đa ×1,15).
3. **Cắt hoặc đệm** cho đúng độ dài chunk, để chunk sau bắt đầu đúng giờ.

## 2. Hai cách

| | Cách cũ: `place_on_timeline_pydub` | Cách mới: `place_on_timeline_ffmpeg` |
|---|---|---|
| Giải mã câu | Mỗi câu pydub mở **1 tiến trình FFmpeg**, chạy lần lượt (khoảng 0,1–0,2 s mỗi câu) | **Một tiến trình FFmpeg** đọc tất cả câu |
| Dựng chunk | Nối dần trong Python; mỗi lần nối sao chép lại cả đoạn đã có | Bộ lọc `concat` nối [lặng, câu, lặng, câu, …] |
| Tăng tốc khi tràn | Xuất WAV, chạy FFmpeg `atempo`, đọc lại | `atempo` trong cùng lệnh |
| Cắt hoặc đệm, mã hóa MP3 | Thêm 1 lượt FFmpeg | `apad` + `atrim` trong cùng lệnh |
| Số tiến trình FFmpeg | khoảng **số câu + 2** | **1** |

**Không đổi:** cách tính mốc (cùng hàm `plan_onsets`), hệ số tăng tốc tối đa, độ dài đầu ra, và các chỉ số `TimelineResult` (`raw_length_sec`, `max_delay_sec`, `tempo_applied`).

**Hai điểm kỹ thuật phải xử lý:**
1. **Độ dài câu:** không lấy từ header MP3. `ffprobe` đọc **dư khoảng 35–45 ms mỗi câu** vì tính cả phần đệm của bộ mã hóa; qua 190 câu sẽ lệch dồn vài giây. Lỗi này được test `test_ffmpeg_engine_places_sentences_where_pydub_does` phát hiện. Cách mới dùng độ dài chính xác code đã đo sẵn lúc tạo giọng (`SynthesisResult.duration_sec`).
2. **Không để sai số dồn:** mỗi câu được `apad` và `atrim` về **đúng ô thời gian** của nó. Sai số nhỏ của từng câu không ảnh hưởng tới vị trí các câu sau.

**An toàn:** cách mới lỗi thì **tự quay về cách cũ** và ghi cảnh báo `Ghep bang 1 lenh FFmpeg that bai`. Chọn cách ghép bằng `TIMELINE_ENGINE=ffmpeg|pydub`, mặc định `ffmpeg`.

## 3. Đo trên dữ liệu giả lập giống thật

Chạy `scripts/bench_timeline.py`, trung bình 3 lần, trong container worker.
- Các câu cắt từ bài TED-Ed, mỗi câu dài 1,5–4,5 s, mã hóa giống Azure (MP3 16 kHz mono 32 kbps).
- Khoảng 20% câu đã tăng tốc bằng `change_tempo`, có cả câu tràn sang câu sau.

| Cỡ | Cách cũ | **Cách mới** | Nhanh hơn |
|---|---|---|---|
| 63 câu / 376 s (bài 6 phút) | 7,04 s | **0,93 s** | khoảng 7,6 lần |
| 122 câu / 566 s (bài 9,4 phút) | 14,51 s | **1,48 s** | khoảng 9,8 lần |
| 190 câu / 600 s (chunk 10 phút đầy) | 20,75 s | **1,86 s** | khoảng 11 lần |
| 190 câu / 480 s (chunk tràn, tăng tốc ×1,15) | 21,52 s | **1,60 s** | khoảng 13 lần |

**Kết quả có giống nhau không:**

| Cỡ | Độ dài (cũ / mới) | Câu lệch mốc nhiều nhất (cũ / mới) | Tương quan đường bao âm lượng |
|---|---|---|---|
| 63 câu | 376,000 / 376,000 s | 0 / 0 ms | 0,9988 |
| 122 câu | 566,000 / 566,000 s | 30 / 15 ms | 0,9987 |
| 190 câu | 600,000 / 600,000 s | 10 / 0 ms | 0,9976 |
| 190 câu, tràn | 480,000 / 480,000 s | 295 / 300 ms (*) | 0,9784 |

- Hai chỉ số trễ tối đa (`max_delay_sec`) và hệ số tăng tốc (`tempo_applied`) trùng nhau ở mọi cỡ.
- (*) Ở ca tràn, script kiểm tra so với mốc **trước khi** tăng tốc nên cả hai cách đều lệch khoảng 300 ms như nhau. Đây là giới hạn của script, không phải lỗi đặt câu.
- Tương quan 0,978 ở ca này vì hai cách chạy `atempo` ở hai định dạng mẫu khác nhau (WAV 16-bit so với float). Khác biệt rất nhỏ.
- **Vì sao so đường bao âm lượng, không so dạng sóng:** mã hóa MP3 lại làm lệch pha từng mẫu. Hai file nghe giống hệt nhau vẫn có tương quan dạng sóng chỉ khoảng 0,7–0,8, nên chỉ số đó không phản ánh đúng.

## 4. Đo bằng job thật

Cùng bài 3462 (lec01, 9 phút 26 giây, **122 câu**):

| Job | Cách ghép | Bước `ghep` trong log TIMING |
|---|---|---|
| 35 (21/11, tiếng Việt) | pydub | **24,4 s** (có kèm khoảng 1–2 s tạo embedding cho Tutor) |
| 42 (22/11, tiếng Nhật) | **ffmpeg** | **1,4 s** |

Dòng TIMING của job 42:
```
asr=0.0s dich=8.8s tts=13.5s ghep=1.4s nhac=65.2s upload=18.8s tong=107.8s
```
- Người dùng thấy job hoàn tất sau khoảng **125 s**.
- Thời gian còn lại là chờ tách nhạc lần đầu trên GPU (bài này chưa có nhạc trên B2). Worker sau đó chạy tiếp khoảng 2,5 phút để tải nhạc lên B2, chạy nền và không ảnh hưởng người xem.

**Ước tính cho chunk 10 phút đầy (khoảng 190 câu):** bước ghép từ khoảng 30–40 s xuống còn khoảng **2–3 s**, tức mỗi chunk nhanh hơn khoảng 30 s.

## 5. Kết luận

- Nhanh hơn **8–17 lần** ở bước ghép, kết quả tương đương cách cũ, logic cốt lõi giữ nguyên, và có tự quay về cách cũ khi lỗi. **Đề xuất đưa vào luồng chính** với `TIMELINE_ENGINE=ffmpeg`.
- **Nhược điểm đã biết:**
  1. Một lệnh FFmpeg có hàng trăm đầu vào. FFmpeg 7 trong container chạy được; với các bản rất cũ chưa có cú pháp `-/filter_complex` thì sẽ tự quay về cách cũ.
  2. Cần độ dài câu do caller truyền vào để tính mốc chính xác. Nếu không có thì hàm tự giải mã song song để đo, chậm hơn nhưng vẫn đúng.
- **Kiểm thử:** `tests/test_timeline.py` chạy cho **cả hai cách** (đệm đủ độ dài, tăng tốc khi tràn, câu đặt đúng chỗ như cách cũ, tự quay về khi lỗi). Toàn bộ: **128 passed**, 6 skipped.
