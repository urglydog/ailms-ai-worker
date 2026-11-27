# Dây chuyền xử lý chunk, tua tới đoạn chưa lồng tiếng, upload B2 không treo (22/11/2026)

Nhánh: `perf/dubbing` (ai-worker) và `feat/dubbing` (fe). Tiếp theo [CaiTien_TachNhacSongSong.md](CaiTien_TachNhacSongSong.md).

## 1. Dây chuyền 2 công đoạn cho bài nhiều chunk (ai-worker, `dubbing_service.py`)

- **Trước:** các chunk chạy lần lượt. Chunk 1 phải xong hẳn (nhận dạng, dịch, tạo giọng, ghép, trộn nhạc, tải lên) rồi chunk 2 mới bắt đầu nhận dạng.
- **Sau:** mỗi chunk tách thành 2 công đoạn:
  - **A** (`_prepare_chunk`): nhận dạng giọng nói, dịch. Dùng Groq và Gemini.
  - **B** (`_finish_chunk`): tạo giọng, ghép theo mốc, trộn nhạc nền, tải lên B2, báo về backend. Dùng Azure, FFmpeg và B2.

  **A của chunk k+1 chạy cùng lúc với B của chunk k.** Hai công đoạn dùng dịch vụ khác nhau nên không tranh nhau Azure, và chunk 1 không bị chậm đi.
- **Giữ an toàn:**
  - B chạy **lần lượt theo thứ tự chunk**, nên backend nhận kết quả **đúng thứ tự, từng cái một**. `InternalDubbingService.upsertChunk` tìm hoặc tạo transcript rồi cộng `doneChunks`; 2 lần báo về đồng thời có thể tạo trùng transcript hoặc đếm sai.
  - Số thứ tự câu của chunk k+1 tính từ số câu ASR của chunk k, như cũ.
  - **Thử lại riêng từng công đoạn** (BR-CHUNK-04, tối đa 3 lần). Thử lại B **dùng lại kết quả của A**, nên không chạy lại Whisper và số câu không đổi giữa các lần thử.
  - Chunk báo không đủ lời thoại (SKIPPED, BR-DUB-10) ở bất kỳ đâu thì cả job vẫn được đánh dấu bỏ qua như cũ.
- **Log:** TIMING thêm mục `cho_chunk_truoc`, là thời gian A đã xong và đang chờ B của chunk trước.
- **Số đo**, job 46 (bài 3464, 11 phút 58 giây, 2 chunk, tiếng Nhật, dùng lại transcript và nhạc):
  - A của chunk 2 đã xong trong lúc chunk 1 còn làm B (`cho_chunk_truoc=200.4s`).
  - Chunk 2 xong **20 s sau chunk 1**: chỉ còn làm B (tạo giọng 8,4 s, ghép 0,4 s, nhạc 1,7 s, tải lên 9,5 s).
  - Với bài 20 phút (2 chunk đầy), A của chunk 2 khoảng 15–25 s, đó là phần được giấu đi nhờ chạy chồng.

## 2. Tua tới đoạn chưa lồng tiếng xong (fe, `lib/player/resolveAudio.ts`)

- **Trước:** mốc đang xem chưa có chunk thì `resolveAudio` lấy `track.chunks[0]` làm mặc định. Trình phát phát file chunk đầu với offset sai, vị trí vượt quá độ dài file, nên học viên **nghe im lặng** mà không có thông báo.
- **Sau:**
  - Trả về `src: null` để trình phát dùng **tiếng gốc của video**, kèm `pending: true`.
  - Nhãn trên trình phát ghi "Đoạn này đang được lồng tiếng — tạm phát tiếng gốc".
  - Chunk đó xong thì trang tự tải lại danh sách chunk (sẵn có) và trình phát chuyển sang bản lồng tiếng.
- Đã thử trên trình duyệt với bài 3464; người dùng xác nhận chạy ổn.
- **Test:** `lib/player/resolveAudio.test.ts` (5 trường hợp). Toàn bộ frontend: 634 passed.

## 3. Upload B2 không còn treo 60 s mỗi lần (ai-worker, `app/storage.py`)

- **Vấn đề:** boto3 mặc định chờ **60 s** mỗi lần kết nối hoặc đọc bị treo rồi mới thử lại. Job 46 tải lên một chunk 7 MB mất **181,9 s**, khoảng 3 lần 60 s, trong khi bình thường chỉ 2–9 s. Backend xử lý lời báo về chỉ 0,37 s. Các lần chậm bất thường trước (219 s ở job 35, lưu nhạc 182 s ở job 40) có cùng kiểu.
- **Sửa:** `connect_timeout = 10 s`, `read_timeout = 30 s`, thử lại tối đa 5 lần kiểu `standard`. Đổi được qua `B2_CONNECT_TIMEOUT_SEC`, `B2_READ_TIMEOUT_SEC`, `B2_MAX_ATTEMPTS`.
  - Hết hạn chờ chỉ xảy ra khi **không có byte nào đi hoặc về** trong suốt khoảng chờ. Mạng chậm nhưng vẫn chạy thì không bị cắt.
  - Một lần treo giờ chỉ tốn khoảng 30 s.
- **Kiểm tra thật:** tải lên 2 MB, 4 lần:
  - lần đầu 44,5 s, nhiều khả năng gặp đúng một lần treo rồi tự phục hồi sau khoảng 30 s;
  - 3 lần sau 3,6 s, 1,8 s và 1,4 s.
- **Test:** `tests/test_storage_config.py`. Toàn bộ worker: 147 passed.

## 4. Ảnh hưởng tới bài NCKH

- Độ khớp thời lượng (Bảng 2, Bảng 3): **không** ảnh hưởng.
- Thời gian xử lý (Bảng 4): **có** với bài dài hơn 10 phút (3 trên 4 bài thử nghiệm). Tổng thời gian và thời gian tới các đoạn sau giảm; thời gian tới đoạn đầu không đổi.
- Đã ghi vào `NCKH/CAP_NHAT_SAU_TOI_UU_DUBBING.md`, mục 5.5.
