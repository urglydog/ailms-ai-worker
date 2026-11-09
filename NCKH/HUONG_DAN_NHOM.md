# Hướng dẫn tiếp tục bài báo NCKH (SSRC-II'2026)

> File này dùng làm **context cho AI (Claude) của thành viên trong nhóm**. Đưa nguyên file cho Claude
> và nói: *"Đọc NCKH/HUONG_DAN_NHOM.md rồi tiếp tục công việc ở mục 6."*
> Claude: đọc hết file này trước khi làm bất cứ việc gì. Trả lời bằng **tiếng Việt**.

---

## 1. Bối cảnh

| Mục | Nội dung |
|---|---|
| Hội nghị | SSRC-II'2026, Khoa CNTT, ĐH Công nghiệp TP.HCM — https://ssrc.fit.iuh.edu.vn/conf/announcement/view/4 |
| Hạn | **15/11/2026 nộp bài** · 22/11 có kết quả phản biện · 04/12 nộp bản chính thức · 11/12 hội nghị |
| Chủ đề nộp | **Chủ đề 4 – Khoa học máy tính & Khoa học dữ liệu** (mục *Speech recognition*, *NLP/Language Model*, *Applications of ML – edtech*). Dự phòng: Chủ đề 2 (*Web-based Education Systems*). |
| Tên bài | *Pipeline lồng tiếng tự động cho video bài giảng trực tuyến với cơ chế điều chỉnh tốc độ đọc thích ứng* |
| Ngôn ngữ | Tiếng Việt (có thể dịch sang tiếng Anh sau khi bản Việt ổn) |
| Tác giả | Nguyễn Hữu Sang, Nguyễn Chí Thiện; GVHD: ThS. Nguyễn Thị Hoàng Khánh (email: bổ sung sau) |
| Hệ thống gốc | Khóa luận "AI-Powered LMS" (nền tảng **LinguaLearn**). Bài báo chỉ trình bày **phần pipeline lồng tiếng AI**, không kể lại toàn bộ LMS. |

## 2. Cấu trúc thư mục

```
NCKH/                         (nằm trong repo ai-worker: project/ai-worker/NCKH)
├── HUONG_DAN_NHOM.md         ← file này
├── format/                   template gốc của hội nghị (KHÔNG sửa)
│   ├── SSRC_template/        main.tex mẫu (IEEEtran + vietnam), tns1.png, tns2.png
│   ├── SSRC_template.pdf
│   └── SSRC_Word_Template.docx
├── resources/
│   └── AI-Powered_LMS.docx   báo cáo khóa luận (nguồn nội dung, chỉ đọc)
├── paper/                    ← MÃ NGUỒN BÀI BÁO
│   ├── main.tex              toàn bộ bài báo (1 file)
│   ├── main.pdf              bản biên dịch gần nhất
│   └── SSRC_LongTieng_overleaf.zip   (đóng gói để upload Overleaf)
└── experiments/              ← SCRIPT ĐO SỐ LIỆU
    ├── run_experiment.py     chạy 4 phương án V1–V4, ghi CSV từng câu
    ├── analyze.py            tổng hợp CSV -> bảng số liệu + dòng LaTeX + biểu đồ
    ├── server_job_stats.py   đọc số liệu job thật trên server (CHỈ ĐỌC)
    ├── server_job_stats.sql  các câu SELECT dùng cho script trên
    ├── videos.example.json   mẫu danh sách video thử nghiệm
    └── results/              kết quả đo (mỗi lần chạy 1 thư mục)
```

## 3. Quy tắc bắt buộc

1. **Định dạng**: giữ nguyên preamble của template SSRC (`\documentclass{IEEEtran}`, `\usepackage[utf8]{vietnam}`,
   `cite`, `amsmath`, `graphicx`…). Chỉ được thêm gói không đổi layout (đã thêm: `xcolor`, `tikz`, `algorithm`,
   `algpseudocode`). Không đổi font, lề, cỡ chữ, số cột.
2. Yêu cầu template: tóm tắt **150–250 từ, 1 đoạn**, không viết tắt, không trích dẫn, không công thức;
   Index Terms 3–6 từ khóa theo **thứ tự chữ cái**; tài liệu tham khảo theo **chuẩn IEEE** (`thebibliography`
   trong main.tex, không dùng file .bib); hình/bảng phải được nhắc trong văn bản; bảng là LaTeX, không chèn ảnh bảng.
3. **Số liệu kỹ thuật phải lấy từ code thật** (repo `project/ai-worker`, `project/be`), không lấy từ tài liệu cũ.
   Báo cáo khóa luận có chỗ đã lỗi thời (xem mục 5).
4. Chỗ chưa có dữ liệu đánh dấu bằng `\todo{...}` (hiện chữ đỏ). **Xóa hết `\todo` trước khi nộp.**
5. **Server**: chỉ được ĐỌC (SELECT). Không tạo job, không sửa/xóa dữ liệu, không restart dịch vụ.
   Dữ liệu trên server thuộc bạn trong nhóm — hỏi Sang trước khi làm gì ngoài việc đọc.
6. Không commit mật khẩu, API key, chuỗi kết nối DB. Dùng biến môi trường.
7. Chỉ commit/push khi người dùng yêu cầu.
8. Tài liệu tham khảo phải **có thật**; không bịa số trang/năm. Không chắc thì hỏi lại hoặc bỏ.

## 4. Biên dịch bài báo

**Overleaf**: New Project → Upload Project → chọn `paper/SSRC_LongTieng_overleaf.zip` (hoặc tạo zip mới chỉ chứa `main.tex`) → Recompile.

**Máy local (MiKTeX, Windows)** — đứng ở thư mục `NCKH/paper`, chạy 2 lần để cập nhật tham chiếu:
```bash
pdflatex -interaction=nonstopmode -output-directory=build main.tex
pdflatex -interaction=nonstopmode -output-directory=build main.tex
```
Rồi copy `build/main.pdf` ra `paper/main.pdf`. Kiểm tra log: không có dòng `!` (lỗi), không có `Overfull \hbox` lớn,
không có `undefined` reference.

## 5. Sự thật kỹ thuật (đã đối chiếu với code)

| Thành phần | Giá trị thật | Nguồn trong code |
|---|---|---|
| Chia đoạn | Cố định **10 phút** (600 s), đoạn cuối chứa phần dư | `ai-worker/app/services/dubbing_service.py` `split_into_chunks`, `config.chunk_minutes` |
| Retry | **3 lần**/đoạn, backoff mũ; hết retry giữ **audio gốc** riêng đoạn đó | `_process_chunk_with_retry`, `config.max_retry` |
| Bỏ qua đoạn không lời | lời thoại < **10%** thời lượng | `MIN_SPEECH_RATIO = 0.10` |
| ASR | Groq API, **whisper-large-v3-turbo**; bỏ qua nếu bài đã có transcript gốc | `app/providers/groq_asr.py`, `config.groq_asr_model` |
| Dịch | **2 lời gọi Gemini / đoạn** (dịch sát nghĩa → biên tập theo `budget_sec`) — gọi là "dịch hai pha" (KHÔNG phải "3 bước" như khóa luận) | `app/services/translation.py` `translate_batch` |
| LLM | Theo `.env` local: **`gemini-3.5-flash`** (code mặc định `gemini-2.5-flash` nếu env không đặt). Ghi vào bài đúng model đã dùng khi đo — `run_meta.json` có lưu. Hỏi Sang model trên server. | `config.gemini_model`, `.env` `GEMINI_MODEL` |
| TTS | **Azure Speech REST + SSML** `<prosody rate>` (KHÔNG phải Edge-TTS) | `app/providers/azure_tts.py` |
| Tỷ số tốc độ | **R = T_tts / T_orig** (code đảo chiều so với tài liệu "T_orig/T_exp" để có nghĩa) | `_speech_rate` |
| Nhánh | R ≤ 1.0 → đệm lặng; 1.0 < R ≤ 1.3 → tăng tốc `(R−1)·100%`; R > 1.3 → LLM rút gọn, tối đa **M = 2** lần, vẫn > 1.3 thì dùng **+30%** và log cảnh báo | `_synthesize_with_adaptive_rate`, `max_resummarize_attempts=2`, `MAX_TTS_RATE="+30%"` |
| Ghép | Chèn khoảng lặng gốc trước mỗi câu, đệm cuối đoạn → mỗi đoạn đúng thời lượng | `audio_utils.concat_with_leading_silence`, `pad_silence` |
| Chống trùng | Redis `SETNX` theo (lessonId, targetLanguage) | `be/.../dubbing/service/DubbingLockService.java` |
| Tái sử dụng | 1 bản lồng tiếng / (bài, ngôn ngữ) dùng chung; transcript gốc dùng lại cho ngôn ngữ khác | `dubbing_service.py` (`reuse_source`), BE `DubbingRequestService` |
| Hạn ngạch | 15 job/ngày (học viên), 30 (giảng viên) | BE `DubbingQuotaService` |
| Player | Dual Player: video tắt tiếng + audio riêng, đồng bộ chu kỳ **250 ms**, hỗ trợ YouTube IFrame API | FE |
| Kiến trúc | Spring Boot (nghiệp vụ) + Python FastAPI/Celery (AI) qua Redis; tiến độ Redis Pub/Sub → WebSocket; lưu trữ S3-compatible (Backblaze B2) | |
| DB | MySQL: `ai_jobs` (started_at, finished_at, total_chunks…), `audio_tracks`, `audio_chunks` (created_at), `transcripts` (is_source), `transcript_segments` (speech_rate, was_summarized) | `be/.../dubbing/entity/*` |

## 6. Việc cần làm (trạng thái ngày 09/11/2026)

### Đã xong
- [x] Khung bài báo đầy đủ 6 mục: Giới thiệu, Nghiên cứu liên quan, Phương pháp (hình pipeline TikZ, công thức R,
      chính sách 3 nhánh, Thuật toán 1), Triển khai, Thực nghiệm (khung), Kết luận; 11 tài liệu tham khảo thật.
- [x] Biên dịch sạch (không lỗi, không overfull).
- [x] Script đo: `run_experiment.py`, `analyze.py`, `server_job_stats.py/.sql` (đã viết, **chưa chạy**).

### Còn lại (theo thứ tự ưu tiên) — trước bước 2, 3 hỏi các thông tin ở mục 7
1. **Chọn 3–5 video** bài giảng tiếng Anh công khai (CNTT + kỹ năng mềm, 5–20 phút) → tạo
   `experiments/videos.json` theo mẫu `videos.example.json`.
2. **Chạy đo local** (khi hệ thống đã tối ưu xong — hỏi Sang trước):
   ```bash
   cd project/ai-worker            # để nạp đúng .env (GROQ/GEMINI/AZURE key)
   python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --max-chunks 1   # chạy thử rẻ
   python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --keep-audio     # chạy thật
   python NCKH/experiments/analyze.py NCKH/experiments/results/<run_id>
   ```
   ASR được cache trong `experiments/.cache/` → chạy lại không tốn Groq.
3. **Lấy số liệu server** (chỉ đọc; thời gian xử lý thật, thời gian ra đoạn đầu, phân bố speech_rate/was_summarized):
   mở SSH tunnel, đặt biến `NCKH_DB_HOST/PORT/USER/PASSWORD/NAME`, `pip install pymysql`, chạy
   `python NCKH/experiments/server_job_stats.py`. Sau đó `analyze.py <run_dir> --server <server_dir>`.
4. **Điền số liệu vào `paper/main.tex`**:
   - Mục *Thiết lập thực nghiệm*: số video N, tổng phút X, cấu hình máy (local) và server.
   - Bảng `tab:results`: dán các dòng LaTeX mà `analyze.py` in ra.
   - Có thể thêm hình `figures/r_hist.pdf` (phân bố R một pha vs hai pha) — nhớ thêm vào zip Overleaf.
   - Viết mục *Kết quả* và *Thảo luận*; sửa câu kết quả trong **Tóm tắt** (vẫn giữ 150–250 từ).
5. (Tùy chọn) **Đánh giá cảm nhận (MOS)**: 5–10 người nghe các file `--keep-audio` của V2 và V4, chấm 1–5 cho
   độ tự nhiên và độ khớp hình.
6. Bổ sung email 3 tác giả, ngày nộp trong `\thanks{}`; kiểm tra dòng `\markboth` (Volume/số của SSRC-II'2026).
7. Rà lại toàn bài, xóa hết `\todo`, biên dịch, nộp trên hệ thống SSRC trước **15/11/2026**.

## 7. Thông tin cần hỏi trước khi đo (AI: hỏi người dùng, KHÔNG tự đoán)

Trước khi chạy bước 2–3 ở mục 6, hỏi người dùng các thông tin sau. **Không yêu cầu người dùng dán mật khẩu,
API key hay private key vào chat** — hướng dẫn họ tự đặt vào biến môi trường hoặc file `.env` (không commit).

**A. Đo local (`run_experiment.py`)**
1. Hệ thống đã tối ưu xong, được phép chạy đo chưa? (Sang đang tối ưu — phải có xác nhận.)
2. File `project/ai-worker/.env` đã có `GROQ_API_KEY`, Gemini key, Azure Speech key/region chưa? (Chỉ hỏi "đã có
   chưa", không hỏi giá trị.) Python env nào dùng để chạy `ai-worker` (venv / Docker container)?
3. Danh sách 3–5 video (link YouTube hoặc file .mp4), nhóm CNTT/Kỹ năng mềm, giọng đọc tiếng Việt muốn dùng.
4. Ngân sách API: được chạy đầy đủ hay chỉ `--max-chunks 1`? Có giữ audio (`--keep-audio`) để đánh giá MOS không?
5. Cấu hình máy chạy (CPU, RAM, tốc độ mạng) — để ghi vào mục Thiết lập thực nghiệm.

**B. Đọc số liệu server (`server_job_stats.py`)** — chủ server là bạn trong nhóm, chỉ được ĐỌC:
1. Địa chỉ server (IP/domain) và **user SSH**; đăng nhập bằng SSH key hay mật khẩu (người dùng tự nhập khi `ssh` hỏi).
2. MySQL chạy **trong Docker** (tên container? có publish cổng 3306 ra host không?) hay cài thẳng trên máy?
3. Tên database, **user MySQL** (tốt nhất là user chỉ có quyền SELECT); mật khẩu người dùng tự đặt vào
   biến môi trường `NCKH_DB_PASSWORD`.
4. Phiên bản code đang chạy trên server (nhánh/commit) — để ghi vào bài và để chắc schema khớp với
   `server_job_stats.sql` (bảng `ai_jobs`, `audio_tracks`, `audio_chunks`, `transcripts`, `transcript_segments`).
5. Khoảng thời gian/job nào nên loại bỏ (job test lỗi, job trước khi đổi sang Azure TTS…).

Cách kết nối gợi ý (sau khi có thông tin):
```bash
# Cửa sổ 1: mở tunnel (MySQL trên host)
ssh -N -L 3307:127.0.0.1:3306 <user>@<server>
# MySQL trong Docker không publish cổng: lấy IP container trên server
#   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <mysql_container>
#   rồi: ssh -N -L 3307:<ip_container>:3306 <user>@<server>

# Cửa sổ 2 (PowerShell): biến môi trường chỉ tồn tại trong phiên này
$env:NCKH_DB_HOST="127.0.0.1"; $env:NCKH_DB_PORT="3307"
$env:NCKH_DB_USER="<user>"; $env:NCKH_DB_NAME="<db>"
$env:NCKH_DB_PASSWORD = Read-Host "MySQL password"   # người dùng tự gõ
pip install pymysql
python NCKH/experiments/server_job_stats.py
```
Phương án thay thế nếu không mở tunnel được: copy `server_job_stats.sql` lên server, chạy
`docker exec -i <mysql_container> mysql -u <user> -p <db> < server_job_stats.sql > out.tsv` và gửi file kết quả về.

## 8. Giải thích script đo (để AI không phải đọc lại code)

- `run_experiment.py` import trực tiếp hàm của pipeline, **không sửa code app**, **không ghi DB**.
  - ASR 1 lần/video (cache) → với mỗi đoạn gọi Gemini 2 lần, lấy kết quả **pha 1 cho V1**, **pha 2 cho V2–V4**.
  - V1/V2: TTS tốc độ mặc định (câu ngắn được đệm lặng, câu dài bị tràn).
  - V3: chỉ tăng tốc tới +30%, không rút gọn.
  - V4: gọi đúng `dubbing_service._synthesize_with_adaptive_rate` (phương án đề xuất).
  - Đếm số lời gọi LLM/TTS bằng cách bọc hàm ở mức module.
  - `segments.csv`: `t_orig, t_tts_default, r_default, branch, applied_rate, n_resummarize, t_final, overrun, abs_delta, llm_calls, tts_calls`.
  - `videos.csv`: thời gian từng giai đoạn (giây), số lời gọi.
- `analyze.py`: Δ trung bình/trung vị/p95, % câu còn tràn, % R>1.3, số lời gọi LLM theo phương án; phân bố
  nhánh; thời gian/phút video; xuất `summary.md`, `summary.json`, dòng LaTeX cho Bảng `tab:results`.
- Khi script lỗi do code app đã đổi (tên hàm/tham số), sửa **script**, không sửa app trừ khi được yêu cầu.
