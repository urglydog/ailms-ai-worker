# Tách nhạc nền song song trên nhiều GPU, và các tối ưu B, C (22/11/2026)

Nhánh `perf/dubbing`. Tiếp theo [CaiTien_BuocCuoi_TaiLen.md](CaiTien_BuocCuoi_TaiLen.md). **Không ảnh hưởng bài NCKH**: nhạc nền không nằm trong phần đánh giá, còn B và C chỉ đổi thời gian.

## 1. Vấn đề

Ở lần lồng tiếng đầu, phần lồng tiếng của chunk 1 xong sau khoảng 40 s, nhưng tách nhạc cả bài trên **1 GPU** mất khoảng 80 s (Demucs khoảng 7 s cho mỗi phút audio). Vì vậy chunk 1 phải **ngồi chờ nhạc khoảng 37 s** (job 44).

## 2. Thay đổi

### 2.1. Tách song song (`app/services/background_music.py`)
- **Chia bài thành n phần bằng nhau**, mỗi phần khoảng `BGM_PIECE_SEC = 180` s. n = ⌈thời lượng / 180⌉, tối đa `BGM_MAX_PARALLEL = 6`.
  - Ví dụ: bài 2 phút giữ 1 phần; bài 6 phút thành 3 phần; bài 9–12 phút thành 4 phần.
  - Chia đều để các máy xong gần cùng lúc, vì phần dài nhất quyết định thời gian chờ.
- **Mỗi phần dư `BGM_PIECE_OVERLAP_SEC = 5` s ở mỗi đầu**, vì Demucs tách kém ở sát mép đoạn. Các phần được gửi lên Modal **cùng lúc**; mỗi phần chạy trên một máy GPU T4 riêng.
- **Nối lại** (`stitch_pieces`):
  - bỏ phần dư, giữ lõi của mỗi phần cộng nửa khoảng trộn chéo;
  - nối bằng `acrossfade` dài `BGM_CROSSFADE_SEC = 0,5` s;
  - cắt theo **số mẫu**, và mốc cắt được làm tròn tới mili-giây ở **cả** lệnh cắt lẫn bước nối, để hai bên dùng cùng một mốc;
  - tổng độ dài đúng bằng bài gốc.
- **Đánh thức đủ n máy** ngay đầu job, vì mỗi máy chạy song song đều phải tự khởi động.
- Đặt `BGM_PIECE_SEC` rất lớn (ví dụ `100000`) thì quay về tách cả bài trên 1 GPU.

### 2.2. Nạp sẵn model trên máy GPU (`modal_apps/demucs_separator.py`)
- **Trước:** mỗi lời gọi chạy lệnh `python -m demucs`, nên lần nào cũng khởi động Python và nạp lại model từ đầu.
- **Sau:** model `htdemucs` được nạp lên GPU **một lần cho mỗi máy**, ngay ở lời gọi đánh thức (mất khoảng 4,7 s), rồi giữ lại cho các lần sau.
  - Các bước xử lý giống hệt lệnh CLI: shifts = 1, overlap = 0,25, chuẩn hóa theo trung bình và độ lệch chuẩn, `clip='rescale'`.
  - Nếu cách mới lỗi thì tự quay về chạy lệnh CLI như cũ.
- File trả về hạ từ 320 kbps xuống **192 kbps cho nhạc** và **96 kbps cho giọng gốc** (giọng gốc chỉ dùng để đo độ to), nên tải về nhẹ hơn khoảng 2 lần.
- Đo trên bài 6 phút 16 giây: Demucs **42–44 s**, trước là 53–57 s.

### 2.3. Tối ưu B: chỉ tải audio gốc khi cần (`app/source_audio.py`)
- Bài đã có bản ký âm, backend đã biết thời lượng, và nhạc nền tắt hoặc đã có trên B2: **không tải lại audio gốc từ YouTube**.
- Chỉ tải khi một bước thật sự cần: chunk lỗi phải giữ audio gốc, chunk không có câu nào, hoặc phải tách nhạc. Dù nhiều bước gọi cùng lúc thì cũng chỉ tải 1 lần.
- Lỗi khi tải vẫn báo `SOURCE_UNAVAILABLE` như cũ (BR-DUB-11).
- **Lý do:** trên server, tải từ YouTube phải đi qua proxy, vừa chậm vừa **dễ bị YouTube chặn**.

### 2.4. Tối ưu C: tạo embedding cho Gia sư AI chạy nền (`dubbing_service._index_for_tutor`)
- Embedding các câu gốc kèm ghi Supabase, dùng cho RAG của Socratic Tutor (UC30), giờ **không chặn** việc tải chunk lên.
- Job đợi bước này xong trước khi dọn thư mục tạm.

## 3. Số đo

**Kiểm tra chỗ nối trên audio thật** (bài TED-Ed 375,8 s, cắt 3 phần có dư 5 s, rồi nối lại):

| | Lần đầu (mốc cắt làm tròn khác nhau) | **Sau khi sửa** |
|---|---|---|
| Lệch ở chỗ nối | +18 mẫu (0,41 ms) và −8 mẫu | **0 mẫu** |
| Tương quan cả bài với bản gốc | 0,8375 | **1,0000** |
| Độ dài | 375,8378 s | 375,8380 s (bản gốc 375,8382 s) |

**Job thật:** job 45, bài 3464 "You're More Stressed Than Ever", 11 phút 58 giây, **2 chunk** (140 + 29 câu), tiếng Việt, **lồng tiếng lần đầu**.

| Mốc | Thời điểm |
|---|---|
| Nhận job | 08:40:40 |
| Tải xong audio gốc, bắt đầu xử lý | +6 s |
| Đánh thức xong 4 máy GPU | +15 s |
| Tách nhạc xong (4 phần song song, Demucs lâu nhất 24,3 s, tổng 56,4 s) | +63 s |
| **Chunk 1 (10 phút đầu) phát được** | **+74 s** |
| Chunk 2 xong | +94 s |
| **Job hoàn tất** | **+97,8 s** |

Dòng TIMING:
```
chunk 0 (140 câu): asr=4.6s dich=19.6s tts=20.6s ghep=1.6s nhac=18.7s upload=2.0s tong=67.2s
chunk 1 (29 câu):  asr=2.0s dich=4.6s  tts=8.2s  ghep=0.4s nhac=1.8s  upload=3.5s tong=20.4s
final=3.7s (2 chunk)
```

**So với trước:**

| | Job 44 (1 GPU, bài 9 phút 13 giây) | **Job 45 (4 GPU, bài 11 phút 58 giây)** |
|---|---|---|
| Demucs | 63,5 s | **24,3 s** (phần lâu nhất) |
| Tổng thời gian tách nhạc | 78,5 s | **56,4 s** (bài dài hơn 30%) |
| Chunk 1 phải chờ nhạc | 36,6 s | **9,9 s** |
| Cả job | 113,8 s (12,3 s mỗi phút video) | **97,8 s (8,2 s mỗi phút video)** |

**Ghi chú:**
- Trong 56,4 s tách nhạc, khoảng 30 s là gửi 4 phần lên và tải 8 file về qua **mạng nhà**, cộng bước nối. Trên server sẽ nhanh hơn.
- Một lời gọi Azure TTS lỗi tạm thời ở lần 1 rồi thành công ở lần thử lại. Không ảnh hưởng kết quả.
- Đo độ to: cả 2 chunk đều ra −18,8 / −21,0 LUFS (hạ 2,2 dB). Đã kiểm tra lại trên file giọng gốc trên B2: các đoạn 0–5 phút, 5–10 phút và 10–12 phút lần lượt là −20,9, −21,1 và −21,0 LUFS. Giọng gốc của bài này đều nên trùng số là hợp lý, không phải lỗi đo.

**Phí GPU ước tính** (T4 0,000164 USD/giây): 4 máy, mỗi máy khoảng 15 s khởi động, khoảng 5 s nạp model và khoảng 25 s Demucs, tổng khoảng 180 giây GPU, tức **khoảng 3 cent cho lần lồng tiếng đầu của bài 12 phút**. Các ngôn ngữ sau dùng nhạc đã lưu trên B2, không tốn GPU. Xem số thật ở mục Credits trên Modal.

## 4. Kiểm thử

- `tests/test_background_music.py`:
  - chia phần khoảng 3 phút;
  - **cắt một tín hiệu thật thành nhiều phần có dư rồi nối lại**, đúng độ dài và khớp bản gốc;
  - đánh thức đủ số máy.
- `tests/test_lazy_source.py`:
  - tải đúng 1 lần dù nhiều bước gọi cùng lúc;
  - lỗi tải báo `SourceUnavailableError`;
  - ngôn ngữ thứ 2 không tải audio gốc, job đầu tải sẵn, chunk lỗi tải khi cần;
  - tạo embedding chạy nền và được đợi trước khi kết thúc.
- Toàn bộ: **143 passed**, 6 skipped.

## 5. Triển khai

- **Deploy lại hàm Modal một lần** (hàm mới có nạp sẵn model): `py -m modal deploy modal_apps/demucs_separator.py`. Đã deploy trên tài khoản sở hữu token hiện tại.
- **Server:** build lại theo mục 6 của [SoSanh_GhepChunk.md](SoSanh_GhepChunk.md). **Không cần thêm biến `.env`**, vì mọi biến mới đều có mặc định.
- **Giới hạn của gói Starter trên Modal:** khoảng 10 GPU chạy cùng lúc (theo các trang tổng hợp). Mỗi job dùng tối đa 6 máy, nên nếu nhiều bài lồng tiếng lần đầu cùng lúc thì có thể phải xếp hàng một chút.
