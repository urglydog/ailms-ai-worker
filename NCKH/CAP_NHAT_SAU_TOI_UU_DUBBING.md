# Cập nhật bài NCKH sau đợt tối ưu dubbing (15–22/11/2026)

**Viết cho:** session/người sửa bài NCKH (`paper/main.tex`) và người đo lại trên server.

**Mục đích:**
- liệt kê pipeline đã thay đổi gì so với bản dùng để đo trong bài;
- mục nào trong bài phải sửa;
- cách đo lại cho đúng.

**Tài liệu chi tiết từng đợt tối ưu** (trong `docs/improve/performance/`):
- `CaiTien_TocDo_Dubbing.md`: chạy song song, rút gọn theo lô, `atempo`, mức suy nghĩ của Gemini, một lời gọi dịch, `max_chars`, embedding theo lô;
- `CaiTien_NhacNen_Dubbing.md`: nhạc nền, mốc theo từ đầu tiên, câu không có chữ để đọc;
- `SoSanh_GhepChunk.md`: ghép bằng một lệnh FFmpeg, checklist build server;
- `CaiTien_BuocCuoi_TaiLen.md`: bước cuối, dung lượng, đánh thức GPU;
- `CaiTien_TachNhacSongSong.md`: tách nhạc song song trên nhiều GPU, nạp sẵn model, chỉ tải audio gốc khi cần, index Gia sư AI chạy nền. **Xem mục 5 bên dưới.**
- `CaiTien_DayChuyen_Chunk.md`: dây chuyền xử lý chunk, tua tới đoạn chưa lồng tiếng, upload B2 không treo. **Mới nhất, xem mục 5.5.**

> **Đọc nhanh cho session NCKH (cập nhật tối 22/11/2026):** những gì **ảnh hưởng bài báo** gồm mục 2 (thuật toán: dịch một lời gọi, `max_chars`, `atempo`, rút gọn theo lô, mốc theo từ đầu tiên), mục 5.1 (**model đổi sang `gemini-3.6-flash`**) và mục 5.5 (dây chuyền chunk làm thay đổi **Bảng 4** với bài dài hơn 10 phút). Còn lại chỉ là tối ưu thời gian, không đổi độ khớp thời lượng. Độ dài đoạn vẫn **L = 600 s**.

---

## 1. Mốc phiên bản

| Phiên bản | Commit (repo ai-worker) | Ghi chú |
|---|---|---|
| **Bản đo trong bài đã nộp (SSRC, 14/11)** | `e5a8cb7` (nhánh `NCKH`, chứa bản sửa 11/11) | Theo `experiments/reports/REPORT_20261111_Thien.md`. **Nên gắn tag** (ví dụ `nckh-ssrc2026-v1`) để tái lập số liệu cũ |
| Tối ưu đợt 1 | `1750975` (`feat/dubbing`) | TTS song song, rút gọn theo lô, `atempo` thay SSML, log TIMING |
| Tối ưu đợt 2 | `ef5266b` (`feat/dubbing`) | **Một lời gọi dịch** kèm `max_chars`, embedding theo lô, dùng lại kết quả khi chunk chạy lại, sửa lỗi khóa token Azure |
| Nhạc nền và sửa lỗi | `38ed361` (`feat/dubbing`) | Nhạc nền (Demucs/Modal), **mốc đầu câu theo từ đầu tiên**, câu không có chữ để đọc thành khoảng lặng |
| Tối ưu ghép và bước cuối | `cf10f29`, `f2caff6`, `7578395` (`perf/dubbing`) | Ghép bằng một lệnh FFmpeg, bỏ ghép file cuối thừa, đánh thức GPU |
| Tối ưu B, C | `4e6fef4` (`perf/dubbing`) | Chỉ tải audio gốc khi cần; index Gia sư AI chạy nền |
| Tách nhạc song song | `34052fb` (`perf/dubbing`) | Nhạc nền chia phần khoảng 3 phút chạy song song trên nhiều GPU; nạp sẵn model Demucs |
| Dây chuyền chunk | `9b165a3` (`perf/dubbing`) | Nhận dạng và dịch của chunk sau chạy cùng lúc với tạo giọng và tải lên của chunk trước. Xem mục 5.5 |
| Upload B2 không treo | `ee0f5f9` (`perf/dubbing`) | Chờ kết nối 10 s, chờ đọc 30 s, thử lại 5 lần (trước 60 s mỗi lần treo). Xem mục 5.5 |
| Trình phát khi tua | `3071339` (repo **fe**, `feat/dubbing`) | Đoạn chưa lồng tiếng xong thì phát tiếng gốc kèm nhãn, thay vì im lặng |
| **Đổi model LLM** | cấu hình `.env`, không phải commit | **`GEMINI_MODEL=gemini-3.6-flash`** (bản đo trong bài là 3.5 Flash). Xem mục 5 |

---

## 2. Thay đổi ảnh hưởng tới nội dung bài (PHẢI sửa `main.tex` hoặc đo lại)

| # | Bài báo đang viết | Code hiện tại | Chỗ cần sửa trong `main.tex` |
|---|---|---|---|
| 1 | **Dịch ngữ cảnh hai pha**: lời gọi 1 dịch sát nghĩa, lời gọi 2 biên tập theo ngân sách thời lượng | **Một lời gọi** (`translation.translate_batch`, prompt `_build_dub_prompt`) vừa dịch vừa viết thành lời nói, mỗi câu kèm `budget_sec` và (nếu có) **`max_chars`**. Lời gọi biên tập riêng **đã bị gỡ** (`_build_adapt_prompt` không còn) | Tóm tắt ("dịch hai pha"); danh sách đóng góp (gạch đầu dòng 2); mục **Dịch ngữ cảnh hai pha**; ô "Dịch hai pha bằng LLM" trong Hình 1; định nghĩa V1/V2 ở mục Thực nghiệm |
| 2 | **`max_chars` chưa có** | Sau lượt tạo giọng đầu, worker đo **tốc độ đọc thật (ký tự/giây) của từng giọng**, lưu Redis `dubbing:tts_cps:{voice}` (làm mượt 0,7 cũ và 0,3 mới). Các job sau dịch với `max_chars = cps × thời lượng câu × 1,15`. **Lần đầu dùng một giọng thì chưa có `max_chars`** | Mục dịch: thêm ràng buộc độ dài theo số ký tự ở tầng prompt (gần với isometric MT nhưng không cần huấn luyện). Nêu rõ trạng thái "lần đầu và sau khi đã có số đo" |
| 3 | **Tăng tốc bằng SSML** `<prosody rate>`, tức **gọi lại TTS** đọc nhanh hơn (Thuật toán 1, dòng 12 và 14; câu "dịch vụ TTS sinh lại câu ở tốc độ mới thay vì kéo giãn tín hiệu") | **Tăng tốc ngay trên file đã có bằng FFmpeg `atempo`** (giữ cao độ), hệ số `min(R, 1,3)` (`dubbing_service._synthesize_segments`, `audio_utils.change_tempo`). Không gọi lại TTS | Mục **Điều chỉnh tốc độ đọc thích ứng**, công thức policy (nhánh 2 vẫn là "tăng tốc tối đa 30%" nhưng cơ chế khác), **Thuật toán 1**, trích dẫn `ssml2010` (có thể bỏ). Ghi chú: `atempo` là kéo giãn tín hiệu, có thể ảnh hưởng độ tự nhiên khác với SSML, nên cần đo lại hoặc ghi vào hạn chế |
| 4 | **Rút gọn từng câu**, mỗi câu một lời gọi LLM, lặp tối đa M = 2 | **Rút gọn theo lô**: mỗi vòng **một lời gọi** cho mọi câu có R > 1,3 và khung ≥ 2 s, mỗi câu kèm `max_chars ≈ len × 1,25 × T_orig / T_tts`. Vẫn M = 2, T_min = 2 s, ngưỡng 1,3 và 1,0. Lời gọi rút gọn lỗi thì chuyển sang tăng tốc tối đa | Thuật toán 1 (vòng `while`, viết theo lô), số lời gọi LLM ở Bảng 2 (286 lời gọi giờ sẽ ít hơn nhiều) |
| 5 | Mốc đầu câu `b_i` là mốc đầu đoạn của Whisper | `b_i` = **thời điểm từ đầu tiên** trong câu (`groq_asr._first_word_start`, dùng mốc theo từ của Groq). Sửa lỗi lời lồng tiếng đè lên nhạc intro: câu 1 bài Crash Course từ 0,0 s thành 3,16 s | Mục Nhận dạng giọng nói (định nghĩa `b_i`). Công thức `eq:onset` **giữ nguyên**. Có thể làm thay đổi độ trễ theo trục thời gian (Bảng 3), nên cần đo lại |
| 6 | Mô hình LLM: Gemini 3.5 Flash | Vẫn Gemini 3.5 Flash nhưng **mức suy nghĩ `minimal`** (`DUBBING_THINKING_LEVEL`) | Bảng 1 (tham số): thêm dòng mức suy nghĩ |
| 7 | Thời gian xử lý khoảng **110 s mỗi phút video** (Bảng 4, hạn chế (iii), phần Vận hành) | Lần lồng tiếng đầu khoảng **12 s mỗi phút** (job 44: bài 9 phút 13 giây xong trong 113,8 s, có nhạc nền); ngôn ngữ sau khoảng 5 s mỗi phút | Bảng 4, đoạn "Vận hành trên hệ thống thật", hạn chế (iii). **Đo lại trên server** |

**Thay đổi nhỏ**, ghi vào bài nếu cần, không bắt buộc:
- Câu chỉ có dấu câu (Whisper hay trả `"."` ở đoạn nhạc) được thay bằng 0,1 s im lặng thay vì gửi TTS.
- Câu bị Gemini bỏ sót khi dịch được dịch lại riêng; vẫn thiếu thì giữ câu gốc.
- Ô "Ghép câu theo khoảng lặng gốc" trong Hình 1 **đã lệch ngay trong bài hiện tại** (phần chữ mô tả cách xếp theo mốc tuyệt đối), nên đổi thành "Xếp câu theo mốc tuyệt đối → âm thanh của đoạn".

## 3. Thay đổi KHÔNG ảnh hưởng nội dung bài (không cần sửa, hoặc chỉ nhắc ở phần Triển khai hay Hướng phát triển)

- **Phân đoạn theo lớp** giữ nguyên: đoạn 600 s xử lý tuần tự, báo tiến độ từng đoạn, thử lại 3 lần, lỗi thì giữ audio gốc, bỏ qua đoạn có lời thoại dưới 10%.
- **Xếp theo mốc tuyệt đối** (`eq:onset`), tăng tốc cả đoạn tối đa ×1,15, khớp đúng độ dài đoạn: **thuật toán giữ nguyên**. Chỉ đổi **cách cài đặt** (một lệnh FFmpeg thay cho pydub); đã kiểm chứng cho kết quả tương đương, xem `SoSanh_GhepChunk.md`.
- Nối các đoạn thành file cuối bằng FFmpeg chép thẳng: dư khoảng 30 ms ở mỗi chỗ nối. Bài đo bài tối đa 15 phút (1 chỗ nối), nên câu "chênh không quá 0,1 giây" vẫn đúng.
- Chống trùng, dùng lại bản lồng tiếng và bản ký âm, trình phát kép: giữ nguyên.
- **Nhạc nền** (tách giọng và nhạc bằng Demucs trên GPU Modal, trộn giữ tỉ lệ gốc) là tính năng mới **không có trong bài**. Có thể nhắc ở Triển khai hoặc Hướng phát triển. **Nên tắt khi đo lại** để số liệu so được với bài cũ (mục 4).
- Embedding theo lô, đánh thức GPU, dung lượng file, bỏ ghép file cuối thừa: chỉ là tối ưu thời gian.
- **Đề xuất còn mở**, chưa làm và không ảnh hưởng bài: tách nhạc theo đoạn và song song; không tải lại video gốc cho ngôn ngữ thứ 2; đưa embedding ra chạy nền.
  - **Ngoại lệ:** **đổi model Gemini** (ví dụ Flash-Lite) **sẽ ảnh hưởng** độ dài và chất lượng bản dịch. **Không đổi model trước khi đo xong.**

## 4. Kế hoạch đo lại

**Bước 0: chuẩn bị code**
1. Merge `perf/dubbing` vào `develop` (nhánh này đã chứa `feat/dubbing`), rồi nhánh `NCKH` merge `develop`.
2. Gắn tag cho bản cũ: `git tag nckh-ssrc2026-v1 e5a8cb7 && git push origin nckh-ssrc2026-v1`.
3. **Sửa `experiments/run_experiment.py`. Hiện chạy LỖI trên code mới:**
   - `_translate_both_phases` gọi `translation._build_adapt_prompt`, hàm này **không còn**.
   - V3 tăng tốc bằng tham số `rate=` của `azure_tts.synthesize`, tức SSML, **không còn là cơ chế của pipeline**.
   - Bộ đếm vá `translation.resummarize`, nhưng pipeline giờ gọi `translation.resummarize_batch`, nên phải vá hàm này (hoặc đếm thẳng `gemini.generate`).
4. **Định nghĩa lại các phương án.** Cần chốt với Sang; đề xuất:
   - **V1**: dịch không ràng buộc độ dài (`_build_direct_prompt`, vẫn còn), tốc độ mặc định.
   - **V2**: dịch theo ngân sách thời lượng (`translate_batch` với `max_chars=None`), tốc độ mặc định.
   - **V3**: V2 cộng `max_chars` (từ tốc độ đọc đo được) cộng tăng tốc `atempo` ≤ ×1,3, **không** rút gọn.
   - **V4**: pipeline đầy đủ hiện tại (`dubbing_service._synthesize_segments`: rút gọn theo lô, `atempo`).
   - Muốn so với bài cũ thì giữ thêm một dòng "bài cũ (`e5a8cb7`)" bằng số liệu đã có. **Không trộn** số liệu cũ và mới trong cùng một phương án.

**Bước 1: chuẩn bị server** (người giữ server)
1. Build lại theo mục 6 của `docs/improve/performance/SoSanh_GhepChunk.md`.
2. **Tắt nhạc nền khi đo:** đặt `BGM_SEPARATION=` (để trống), rồi `docker compose up -d --force-recreate ai-worker`.
3. **Tốc độ đọc của giọng:** ghi lại hoặc xóa khóa Redis `dubbing:tts_cps:vi-VN-*` trước khi đo, vì lần đầu của một giọng không có `max_chars`. Đề xuất chạy V4 **hai lần**:
   - lần 1: chưa có số đo;
   - lần 2: đã có số đo.

   Báo cáo cả hai, hoặc chọn lần 2 làm kết quả chính và ghi rõ.
4. Giữ nguyên: `GEMINI_MODEL` (3.5 Flash), `DUBBING_THINKING_LEVEL=minimal`, `TTS_CONCURRENCY` (mặc định 16), `TIMELINE_ENGINE=ffmpeg`.
5. Ghi commit đang chạy, giá trị `.env` liên quan (không ghi key) và trạng thái các khóa `tts_cps` vào NOTES của đợt đo.

**Bước 2: đo**
- **Cùng 4 bài** như bài cũ (xem `experiments/videos.json`), để so được.
- **Độ khớp thời lượng** (Bảng 2): Δ trung bình, % câu tràn, % R > 1,3, số lời gọi LLM và TTS, chạy bằng `run_experiment.py` đã sửa.
- **Độ trễ theo trục thời gian** (Bảng 3): `check_full_length.py` và `drift_analysis.py` trên âm thanh mới. Lưu ý: mốc `b_i` giờ theo từ đầu tiên.
- **Vận hành** (Bảng 4): lồng tiếng thật 4 bài qua web, lấy thời gian từ `ai_jobs` và `audio_chunks`, cùng dòng log `TIMING`. Xóa bản lồng tiếng và transcript cũ của các bài trước khi chạy, để có lần đầu (có bước nhận dạng giọng nói).
- **Độ bảo toàn ý** (L4): câu rút gọn đã khác, nên **chấm lại 50 câu** (2 người, cùng quy trình và hạt giống cố định).
- Nếu chạy lại MOS: chấm trên audio của bản mới.

**Bước 3: sửa `main.tex`** theo mục 2, thay số liệu mới.
- Nếu không kịp đo lại, **phương án tối thiểu**: giữ mô tả và số liệu bản `e5a8cb7`, thêm một đoạn ở Triển khai hoặc Thảo luận rằng sau đánh giá, hệ thống được tối ưu tốc độ (gộp lời gọi dịch, `atempo`, rút gọn theo lô; khoảng 12 s mỗi phút video), **ghi rõ các thay đổi này không nằm trong phần đánh giá**.
- **Không** mô tả thuật toán mới đi kèm số liệu cũ.

---

## 5. Bổ sung 22/11/2026 (chiều): các thay đổi sau khi viết file này

### 5.1. ẢNH HƯỞNG tới bài, phải ghi vào bài và vào NOTES đo lại
- **Model LLM đổi sang `gemini-3.6-flash`.** Người phụ trách dự án chốt 3.6 là bản ổn định nhất. Mức suy nghĩ vẫn là `minimal`; model 3.6 hỗ trợ mức này.
  - Bảng 1 (tham số) trong `main.tex` đang ghi "Gemini 3.5 Flash", **phải sửa thành 3.6 Flash** nếu số liệu mới đo bằng 3.6.
  - Đổi model làm thay đổi độ dài và chất lượng bản dịch, nên Δ, % câu tràn, số câu rút gọn và độ bảo toàn ý **phải đo bằng đúng 3.6**.
  - Kiểm tra trên server: `docker exec lms_ai_worker printenv GEMINI_MODEL` phải ra `gemini-3.6-flash`. `.env` chỉ được nạp khi **tạo lại** container (`up -d --force-recreate`); lệnh `restart` không nạp lại.
  - Ghi model thật đang chạy vào NOTES của đợt đo.

### 5.2. KHÔNG ảnh hưởng nội dung hay độ khớp thời lượng; chỉ đổi thời gian (Bảng 4)
| Thay đổi | Tóm tắt | Ảnh hưởng tới bài |
|---|---|---|
| **Tách nhạc song song** | Nhạc nền được chia thành phần khoảng 3 phút (dư 5 s mỗi đầu), tách cùng lúc trên nhiều GPU T4, nối lại bằng trộn chéo 0,5 s. Đã kiểm tra trên audio thật: khớp bản gốc tới từng mẫu (tương quan 1,0). Model Demucs được nạp sẵn trên mỗi máy | Không: nhạc nền không có trong phần đánh giá. **Nếu bật nhạc nền khi đo** thì chỉ thời gian xử lý (Bảng 4) thay đổi |
| **Tối ưu B: chỉ tải audio gốc khi cần** | Bài đã có bản ký âm (lồng tiếng ngôn ngữ thứ 2) thì không tải lại từ YouTube | Không. Lưu ý khi đo Bảng 4: phải **xóa bản ký âm cũ** để đo đúng lần đầu (có bước nhận dạng giọng nói và có tải audio) |
| **Tối ưu C: index Gia sư AI chạy nền** | Embedding câu gốc kèm ghi Supabase không còn chặn việc tải chunk | Không |
| **Quyết định không đổi độ dài đoạn** | Đã cân nhắc rút đoạn còn 5 phút hoặc cho đoạn đầu ngắn, và **quyết định giữ L = 600 s**: cắt nhiều đoạn hơn thì dễ cắt đôi câu và dịch mất ý | Bài giữ nguyên **L = 600 s** (Bảng 1, mục Phân đoạn theo lớp, BR-CHUNK-02) |

### 5.3. Thời gian xử lý mới nhất (máy local, mạng nhà; chỉ để tham khảo, số cho bài phải đo trên server)
| Job | Bài | Tình huống | Kết quả |
|---|---|---|---|
| 44 | 9 phút 13 giây, 1 chunk | Lần đầu, nhạc nền tách trên 1 GPU | 113,8 s (12,3 s mỗi phút video) |
| **45** | **11 phút 58 giây, 2 chunk** | **Lần đầu, nhạc nền 4 GPU song song** | **Chunk 1 phát được sau 74 s; cả job 97,8 s (8,2 s mỗi phút video)** |
| 43 | 6 phút 16 giây | Ngôn ngữ thứ 2 (dùng lại bản ký âm và nhạc) | 32,7 s |

So với bài đã nộp (khoảng 110 s mỗi phút video, đến đoạn đầu 886–1174 s), thời gian xử lý giảm **khoảng 13 lần**. Câu "chậm hơn thời gian thực" trong hạn chế (iii) **không còn đúng**: hiện xử lý nhanh hơn thời gian thực khoảng 7 lần. Cần sửa sau khi có số đo trên server.

### 5.4. Gợi ý cấu hình khi đo lại trên server (bổ sung cho mục 4, bước 1)
- `GEMINI_MODEL=gemini-3.6-flash`, `DUBBING_THINKING_LEVEL=minimal`, `TIMELINE_ENGINE=ffmpeg` (mặc định).
- **Nhạc nền:** session NCKH đã xác nhận nhạc nền **gần như không ảnh hưởng** độ khớp từng câu. Có thể bật như khi chạy thật, nhưng **ghi rõ trong NOTES** là bật hay tắt, vì nó ảnh hưởng thời gian ở Bảng 4.
  - Nếu bật: hàm `lms-demucs` trên Modal phải là **bản mới** (có nạp sẵn model, commit `34052fb`).
  - Token Modal trong `.env` phải đúng tài khoản đã deploy hàm.
- Build lại theo mục 6 của `docs/improve/performance/SoSanh_GhepChunk.md`.

### 5.5. Bổ sung tối 22/11/2026: dây chuyền chunk, tua, upload B2 (`docs/improve/performance/CaiTien_DayChuyen_Chunk.md`)
| Thay đổi | Ảnh hưởng tới bài |
|---|---|
| **Dây chuyền 2 công đoạn** (commit `9b165a3`): nhận dạng và dịch của chunk sau chạy cùng lúc với tạo giọng và tải lên của chunk trước; báo backend vẫn đúng thứ tự | Không ảnh hưởng độ khớp (Bảng 2, 3). **Có** ảnh hưởng **Bảng 4** với bài dài hơn 10 phút (3 trên 4 bài thử nghiệm: 815, 718, 900 s): tổng thời gian và thời gian tới các đoạn sau giảm; **thời gian tới đoạn đầu không đổi**. Mục "Phân đoạn theo lớp" vẫn đúng (mỗi đoạn xử lý độc lập, báo tiến độ từng đoạn); có thể thêm 1 câu "xử lý theo dây chuyền 2 công đoạn" |
| **Upload B2 chờ ngắn và thử lại** (commit `ee0f5f9`) | Không. Chỉ giảm các lần tải lên chậm bất thường (trước đây có lần 1–3 phút), nên số đo Bảng 4 ổn định hơn |
| **Trình phát tua tới đoạn chưa lồng tiếng** (fe, commit `3071339`) | Không (thuộc giao diện). Có thể nhắc ở mục Trình phát kép: đoạn chưa xong thì phát tiếng gốc |

---

## 6. Kinh nghiệm đo đạc (rút ra từ các lần đo job 29–46, 15–22/11/2026)

Viết cho session viết script đo và người đo trên server. Đây là các bẫy **đã gặp thật** khi đo. Script `run_experiment_v2.py` đã xử lý sẵn một số (tốc độ đọc `tts_cps`, loại câu chỉ có dấu câu, ghi commit); phần dưới liệt kê đủ để đối chiếu.

### 6.1. Đọc log TIMING (nguồn số liệu thời gian cho Bảng 4)
Mỗi chunk ghi một dòng; sau khi có dây chuyền, dòng này có thêm `cho_chunk_truoc`:
```
TIMING job=46 chunk=1 cau=29 asr=0.0s dich=3.7s cho_chunk_truoc=200.4s tts=8.4s ghep=0.4s nhac=1.7s upload=9.5s tong=224.1s
TIMING job=46 final=5.0s (2 chunk)
```

| Trường | Nghĩa | Lưu ý |
|---|---|---|
| `asr` | nhận dạng giọng nói | **0.0s** nghĩa là dùng lại bản ký âm có sẵn, không chạy ASR. Muốn đo lần đầu thì xem mục 6.3 |
| `dich` | dịch (cả gọi lại câu bị thiếu) | 0.0s nếu bản dịch đích đã có sẵn trong DB |
| `cho_chunk_truoc` | công đoạn A đã xong, đang chờ công đoạn B của chunk trước | Chỉ khác 0 từ chunk thứ 2. **Không phải thời gian xử lý** |
| `tts` | tạo giọng, rút gọn theo lô, tăng tốc `atempo` | gồm cả các lời gọi Gemini rút gọn |
| `ghep` | xếp câu theo mốc thành file audio của chunk | **Từ 22/11 không còn gồm** tạo embedding cho Gia sư AI (đã chạy nền). Số trước 22/11 có gồm |
| `nhac` | **chờ** tách nhạc xong, cộng đo độ to và trộn | Bật nhạc nền thì đây gồm cả thời gian chờ GPU. Tắt nhạc nền thì khoảng 0 |
| `upload` | tải chunk lên B2 và báo về backend | Xem mục 6.4 về các lần chậm bất thường |
| `tong` | từ lúc chunk bắt đầu công đoạn A tới khi báo xong | **Gồm cả `cho_chunk_truoc`**. Thời gian xử lý thật của chunk = `tong − cho_chunk_truoc` |
| `final=` | nối các chunk thành file cuối, cộng tải lên | Bài 1 chunk khoảng 0,1 s, vì dùng luôn file chunk |

**Các mốc nên báo cáo**, lấy từ log hoặc từ DB:
- **Thời gian tới đoạn đầu** = mốc log `PUT .../jobs/{id}/chunks/0 204` − mốc `Bat dau pipeline long tieng: job=...`. Có thể lấy từ `audio_chunks`/`ai_job_chunks` nếu bảng có `updated_at`.
- **Tổng thời gian** = dòng `Task app.tasks.dubbing.run_pipeline[...] succeeded in X s`. Mốc **người dùng thấy xong** là dòng `POST .../jobs/{id}/finish 204`, có thể sớm hơn dòng `succeeded` vì job còn đợi các việc chạy nền (lưu nhạc lên B2, index Gia sư AI) trước khi dọn thư mục.

Dòng log về nhạc nền, nếu bật:
- `BGM da danh thuc N may GPU tach nhac: Xs`
- `BGM tach nhac xong: N phan song song, Demucs lau nhat Xs, tong Ys`
- `BGM dung lai nhac da tach tren B2 (...)`: không gọi GPU
- `BGM do to: ... -> chinh ±X dB`
- `BGM tron nhac chunk a-bs: cho Xs, tron Ys`

### 6.2. `parse_worker_logs.py` cần cập nhật
- **`RE_CAP` không còn khớp log mới.**
  - Regex đang tìm `Segment seq=(\d+) van R=([\d.]+) > 1\.3 sau (\d+) lan rut gon`.
  - Log hiện tại là `Segment seq=%s van R=%.2f > 1.3 sau rut gon — tang toc toi da x1.3 ...`, không còn số lần.
  - Nên script sẽ **đếm ra 0** câu chạm trần. Sửa regex thành `Segment seq=(\d+) van R=([\d.]+) > 1\.3`.
- **Nghĩa của cảnh báo đó đã đổi:** giờ nó được ghi cho **mọi** câu còn R > 1,3 khi tăng tốc, **kể cả** câu khung ngắn hơn 2 s không được rút gọn. Muốn tách 2 loại thì kết hợp với `transcript_segments.was_summarized`.
- Nên thêm phần đọc dòng `TIMING` (mục 6.1) để lập Bảng 4 thay vì đo bằng tay.
- `RE_TEMPO` và `RE_CUT` vẫn khớp.

### 6.3. Muốn đo "lần lồng tiếng đầu" thì phải xóa đúng dữ liệu cũ
Hệ thống **dùng lại** rất nhiều thứ. Không xóa thì số đo là của lần thứ 2, nhanh hơn nhiều và **không đúng tình huống bài báo**.

| Dùng lại | Ở đâu | Hệ quả nếu quên xóa |
|---|---|---|
| Bản ký âm gốc | `transcripts` (`is_source=1`) và `transcript_segments` | `asr=0`, không tải audio gốc. **Mốc đầu câu là mốc CŨ**: bản ký âm lưu trước 21/11 dùng mốc đầu đoạn của Whisper, chưa dùng mốc theo từ đầu tiên, nên **Bảng 3 sai** |
| Bản dịch đích | `transcripts` (`is_source=0`, đúng ngôn ngữ) | `dich=0`, bỏ qua Gemini |
| Bản lồng tiếng | `audio_tracks`, `audio_chunks`, `ai_jobs`, `ai_job_chunks` | Web không cho lồng tiếng lại cặp (bài, ngôn ngữ) đó |
| Nhạc đã tách | B2 `bgm/{lesson_id}/{sha1(video_url)[:12]}/music.mp3, vocals.mp3` | Không gọi GPU (nhanh hơn khoảng 60 s) |
| Tốc độ đọc của giọng | Redis `dubbing:tts_cps:{voice}` | Lần đầu của một giọng không có `max_chars`, nên phải đọc lại nhiều câu. Đã ghi lại trong `tts_cps_before/after` |

**Thứ tự xóa an toàn cho một bài** (MySQL; đã dùng nhiều lần ở local):
```sql
DELETE FROM ai_job_chunks WHERE ai_job_id IN (SELECT id FROM ai_jobs WHERE lesson_id=?);
DELETE FROM ai_jobs WHERE lesson_id=?;
DELETE FROM audio_chunks WHERE audio_track_id IN (SELECT id FROM audio_tracks WHERE lesson_id=?);
DELETE FROM audio_tracks WHERE lesson_id=?;
DELETE FROM transcript_segments WHERE transcript_id IN (SELECT id FROM transcripts WHERE lesson_id=?);
DELETE FROM transcripts WHERE lesson_id=?;
```
- **Bẫy đã gặp (job 37):** xóa bản lồng tiếng mà **giữ lại transcript đích** thì worker bỏ qua bước dịch, nhưng backend vẫn chèn lại các câu đích, nên lỗi **500 `Duplicate entry ... uk_segment_transcript_seq`**. Phải xóa **cả** transcript đích, hoặc xóa cả hai transcript.
- Embedding Gia sư AI trên Supabase của bài cũ vẫn còn. Lần chạy sau sẽ ghi thêm một bản trùng. Không ảnh hưởng số đo.
- Thêm hoặc xóa bài trong khóa học: xóa cache Redis `courseDetails::{slug}` để trang hiện đúng. `redis-cli` cần mật khẩu; dễ nhất là chạy Python trong `lms_ai_worker` với `redis.from_url(settings.redis_url)`.

### 6.4. Các bẫy môi trường đã gặp
1. **`.env` chỉ được nạp khi TẠO LẠI container** (`docker compose up -d --force-recreate ai-worker`). `restart` thì không. Đã gặp: `.env` ghi `gemini-3.6-flash` nhưng container vẫn chạy 3.5. Trước mỗi đợt đo, kiểm tra: `docker exec lms_ai_worker printenv GEMINI_MODEL DUBBING_THINKING_LEVEL BGM_SEPARATION`.
2. **Code chạy là code trong thư mục được gắn vào container** (`../ai-worker:/app`), **theo nhánh đang checkout** ở thư mục đó. Đổi nhánh rồi `restart` là đổi code. Ghi commit thật bằng `git -C project/ai-worker rev-parse HEAD`, và xác nhận đúng phiên bản bằng `docker exec lms_ai_worker grep -c _prepare_chunk_with_retry app/services/dubbing_service.py` (phải lớn hơn 0 với bản có dây chuyền).
3. **Upload B2 bị treo:** trước commit `ee0f5f9`, mỗi lần treo mất **60 s** (gặp 182 s và 219 s cho một chunk 7 MB, bình thường 2–9 s). Sau commit đó tối đa khoảng 30 s mỗi lần. Gặp `upload` lớn bất thường thì **ghi chú hoặc chạy lại**, đừng lấy trung bình lẫn vào.
4. **Key Gemini hết hạn hoặc bị thu hồi giữa chừng** (job 39): lỗi `401 API key not valid`, chunk hỏng cả 3 lần thử, job `FAILED ALL_CHUNKS_FALLBACK`. Gọi thử một câu trước khi chạy cả loạt.
5. **Modal (nhạc nền):**
   - GPU chỉ chạy được khi tài khoản đã thêm thẻ.
   - Hàm `lms-demucs` phải là bản mới (commit `34052fb`, có nạp sẵn model).
   - Lần thử GPU **L4** từng phải chờ cấp GPU **585 s**; T4 ổn định (đang dùng T4).
   - Nhiều job lần đầu chạy cùng lúc có thể chạm giới hạn khoảng 10 GPU của gói Starter.
6. **Tải video YouTube trên server** phải qua proxy (đang chết, xem `secrets/README.md`); lỗi tải là `SOURCE_UNAVAILABLE`. Ở local đã tắt proxy bằng `YOUTUBE_PROXY_LIST_PATH: ""`.
7. **Thời gian ở local không đại diện cho server:** mạng tải lên ở nhà chậm và hay treo. Số liệu cho bài báo chỉ lấy trên server.

### 6.5. Bẫy khi đo độ khớp và độ trễ (Bảng 2, 3)
- **Câu chỉ có dấu câu** (Whisper hay trả `"."` ở đoạn nhạc) được pipeline thay bằng **0,1 s im lặng**. `run_experiment_v2.py` đã loại các câu này khỏi mọi phương án. **Báo cáo số câu bị loại**, vì nó làm số câu khác bản cũ.
- **Đo độ trễ trên file đã trộn nhạc là sai:** dò mốc có tiếng trên audio có nhạc nền sẽ bắt nhầm tiếng nhạc. Hãy:
  - đo trên file từng câu (`chunk_{i}_seg_{seq}.mp3`, chỉ còn trong lúc job chạy), hoặc dựng lại bằng `place_on_timeline` như `check_full_length.py`;
  - hoặc chạy job với `BGM_SEPARATION=` (tắt) khi cần đo trên audio cuối.
- **Đừng so dạng sóng của 2 file MP3 bằng tương quan từng mẫu:** mã hóa MP3 lại làm lệch pha, nên 2 file nghe y hệt vẫn chỉ có tương quan khoảng 0,7–0,8. Dùng **tương quan đường bao âm lượng** (RMS mỗi 20 ms, khoảng 0,998 khi khớp) hoặc dò độ lệch tốt nhất cho từng câu. Xem `scripts/bench_timeline.py` trong repo.
- **Độ dài file MP3 trong header (`ffprobe`) dư khoảng 35–45 ms** so với âm thanh giải mã, vì phần đệm của bộ mã hóa. So độ dài cuối bài thì giải mã ra (pydub hoặc FFmpeg), đừng đọc header. Nối nhiều chunk bằng chép thẳng thêm khoảng 30 ms ở mỗi chỗ nối.
- **LLM không tất định:** mỗi phương án nên chạy ít nhất 2 lần nếu còn credit, hoặc ghi rõ "1 lần chạy" như bài cũ.

### 6.6. Số liệu tham khảo để tự kiểm tra (local, mạng nhà)
| Job | Bài | Tình huống | Số liệu chính |
|---|---|---|---|
| 44 | 3465, 9 phút 13 giây, 112 câu, vi | lần đầu, nhạc 1 GPU | xong 113,8 s; `nhac` chờ 36,6 s |
| 45 | 3464, 11 phút 58 giây, 140+29 câu, vi | lần đầu, nhạc 4 GPU | đoạn đầu 74 s, xong 97,8 s; `upload` chunk 0 2,0 s |
| 46 | 3464, ja | ngôn ngữ thứ 2, dây chuyền | `cho_chunk_truoc` 200,4 s (do upload treo 181,9 s); chunk 2 xong 20 s sau chunk 1 |
| 43 | 3463, 6 phút 16 giây, fr | ngôn ngữ thứ 2 | xong 32,7 s; `final` 0,1 s |

Số liệu trên server mà lệch rất xa các mốc này (ví dụ `ghep` hơn 10 s, `tts` hơn 60 s mỗi chunk 10 phút) thì nhiều khả năng sai phiên bản code hoặc sai cấu hình (mục 6.4).
