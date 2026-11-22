# Cải tiến bước cuối, dung lượng tải lên và khởi động GPU (22/11/2026)

Nhánh: `perf/dubbing`, gộp từ `perf/timeline-ffmpeg`. Tiếp theo [SoSanh_GhepChunk.md](SoSanh_GhepChunk.md). Ba điểm 2, 3 và 4 trong đợt khảo sát pipeline; điểm 1 (tách nhạc song song trên nhiều GPU) làm sau.

## 1. Thay đổi

### Điểm 2: bỏ bước ghép file cuối thừa (`dubbing_service.run_dubbing_pipeline`, `audio_utils.concat_files`)
- **Trước:** sau khi các chunk xong, pydub giải mã toàn bộ các chunk, mã hóa lại thành `final.mp3`, giải mã thêm lần nữa để đo độ dài, rồi tải `final.mp3` lên B2. Với bài 1 chunk, file này giống hệt file chunk vừa tải lên.
- **Sau:**
  - **Bài 1 chunk:** dùng luôn file chunk và đường dẫn của nó trên B2 làm `final_url`. Không mã hóa lại, không tải lên lần 2. Backend không xóa file chunk trên B2, nên dùng chung được.
  - **Bài nhiều chunk:** nối bằng FFmpeg `concat` ở chế độ **chép thẳng (`-c copy`)** khi các chunk cùng sample rate và số kênh. Nếu khác, ví dụ có chunk lỗi phải giữ audio gốc, thì nối bằng bộ lọc `concat` và mã hóa lại trong 1 lượt.
  - Độ dài file cuối đọc từ header (`ffprobe`), không giải mã cả bài. Backend chỉ cần số giây nguyên.
  - Log có thêm dòng `TIMING job=… final=…s (N chunk)`.

### Điểm 3: file nhẹ hơn (`background_music.py`)
- Chunk sau khi trộn nhạc: 128 kbps xuống **96 kbps** (`BGM_MIX_BITRATE`), nhẹ hơn khoảng 25%. Với giọng nói và nhạc nền thì gần như không nghe ra khác biệt; cần nghe thử để xác nhận.
- Kết hợp điểm 2: bài 1 chunk chỉ tải audio lên **1 lần**.

### Điểm 4: tách nhạc sớm hơn (`background_music.warm_up`, `modal_apps/demucs_separator.py`)
- **Đánh thức GPU ngay đầu job:**
  - Ngay sau khi lấy thông tin job, worker gửi một lời gọi **rỗng** tới hàm `separate` trên Modal và không chờ kết quả.
  - Container GPU khởi động (khoảng 15–20 s) **song song** với việc tải audio gốc.
  - Hàm trên Modal thấy audio rỗng thì trả về ngay, không chạy Demucs.
  - Bài đã có nhạc trên B2 thì không đánh thức. Tắt được bằng `BGM_WARM_UP=false`.
- **File gửi đi tách nhạc:** MP3 192 kbps xuống **128 kbps** (`BGM_UPLOAD_BITRATE`). Bài 6 phút từ 9,0 MB xuống 6,0 MB.
  - Đã đo thời gian chuyển mã: 192 kbps mất 2,71 s, 128 kbps mất 2,51 s, Opus 128 kbps mất 2,97 s. Chuyển mã vốn nhanh nên không phải chỗ cần tối ưu; lợi ích nằm ở việc gửi file nhẹ hơn.

## 2. Số đo

**Nối file cuối, bài nhiều chunk** (3 chunk, mỗi chunk khoảng 14 phút, MP3 96 kbps stereo):

| | pydub (cũ) | **FFmpeg chép thẳng (mới)** |
|---|---|---|
| Thời gian | 32,7 s | **1,0 s** |
| Độ dài so với tổng 3 chunk (2527,430 s) | 2527,430 s | 2527,489 s (+59 ms, khoảng 30 ms mỗi chỗ nối) |

Chép thẳng MP3 có thể thêm khoảng 1 khung (26–50 ms) ở mỗi chỗ nối. Với chunk 10 phút, lệch đồng bộ cuối bài chỉ vài chục ms cho mỗi chunk, không nghe ra.

**Job thật:** cùng bài 3463 (TED-Ed, 6 phút 16 giây, 63 câu), dùng lại transcript và nhạc đã có trên B2.

| | Job 41 (21/11, tiếng Hàn) | **Job 43 (22/11, tiếng Pháp)** |
|---|---|---|
| Dịch | 8,2 s | 8,8 s |
| Tạo giọng | 8,3 s | 9,5 s |
| Ghép | 8,6 s (pydub) | **0,9 s** (FFmpeg) |
| Nhạc (đo độ to và trộn) | 5,3 s | 5,3 s |
| Tải chunk lên | 4,3 s | **3,5 s** |
| Bước cuối (`final`) | khoảng 23 s | **0,1 s** |
| **Cả job** | **63 s** | **32,7 s** |

Riêng phần đánh thức GPU **chưa đo được**, vì cần một bài chưa từng lồng tiếng (chưa có nhạc trên B2).

## 3. Kiểm thử

- `tests/test_finalize.py`:
  - bài 1 chunk không ghép lại, không tải lên lần 2, và `final_url` là đường dẫn của chunk;
  - bài nhiều chunk có ghép và tải lên;
  - nối khi cùng định dạng (chép thẳng) và khi khác định dạng (mã hóa lại).
- `tests/test_background_music.py`: đánh thức GPU khi bật, bỏ qua khi tắt hoặc khi bài đã có nhạc trên B2.
- Toàn bộ: **135 passed**, 6 skipped.

## 4. Triển khai

- **Phải deploy lại hàm Modal một lần**, vì hàm mới nhận được lời gọi rỗng. Đã deploy trên tài khoản sở hữu token hiện tại (`lms-demucs`).
  - Nếu sau này deploy trên tài khoản khác, chạy `py -m modal deploy modal_apps/demucs_separator.py`.
  - Nếu worker gọi tới hàm cũ chưa deploy lại, lời gọi đánh thức sẽ lỗi. Lỗi này chỉ ghi cảnh báo `BGM khong danh thuc duoc GPU`, không ảnh hưởng job.
- **Server:** làm theo mục 6 của [SoSanh_GhepChunk.md](SoSanh_GhepChunk.md) (build lại `ai-api`, `ai-worker`, `ai-beat`). Không cần thêm biến `.env` mới, vì các biến mới đều có mặc định:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BGM_MIX_BITRATE` | `96k` | Chất lượng chunk sau khi trộn nhạc |
| `BGM_UPLOAD_BITRATE` | `128k` | Chất lượng file gửi đi tách nhạc |
| `BGM_WARM_UP` | `true` | Đánh thức GPU ngay đầu job |
