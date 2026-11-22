# Hướng dẫn đo lại sau đợt tối ưu dubbing (đợt 3, viết ngày 22/11/2026)

> **Dành cho AI (Claude) của thành viên đo.** Đưa nguyên file này cho Claude và nói:
> *"Đọc NCKH/HUONG_DAN_DO_LAI_SAU_TOI_UU.md rồi làm theo, hỏi tôi trước mỗi bước có đánh dấu ❓."*
> Trả lời bằng **tiếng Việt**.
>
> Nên đọc kèm (chỉ để tra cứu, không cần đọc hết): `NCKH/CAP_NHAT_SAU_TOI_UU_DUBBING.md` (pipeline đã đổi gì),
> `docs/improve/performance/SoSanh_GhepChunk.md` mục 6 (checklist build server), `NCKH/HUONG_DAN_NHOM.md` mục 3 và 9.2 (quy tắc chung).

## 0. Bối cảnh trong 5 dòng

- Bài báo SSRC-II'2026 đã nộp ngày 14/11 với số liệu đo trên **bản cũ** (commit `e5a8cb7`, Gemini 3.5 Flash, dịch hai pha, tăng tốc bằng SSML, rút gọn từng câu).
- Sau đó pipeline đã được tối ưu nhiều đợt. `paper/main.tex` **đã được viết lại phần Phương pháp** theo bản mới, nhưng **toàn bộ số liệu (Bảng 2–4, L4, Tóm tắt, Kết luận) vẫn là số cũ**, đánh dấu chữ đỏ `\todo{...}`.
- Hạn nộp **bản chính thức: 04/12/2026**. Cần đo lại trên bản mới và nộp REPORT để Sang kiểm tra rồi mới điền vào bài.
- Bản mới khác bản cũ ở: **một lời gọi dịch có `max_chars`**, **tăng tốc bằng FFmpeg `atempo`** (không gọi lại TTS), **rút gọn theo lô**, **mốc đầu câu theo từ đầu tiên**, **Gemini 3.6 Flash, thinking `minimal`**, **giữ nhạc nền bật**, **dây chuyền 2 công đoạn** cho bài nhiều chunk.
- Độ dài đoạn vẫn là **L = 600 s**; xếp câu theo mốc tuyệt đối, tăng tốc cả đoạn tối đa ×1,15 **không đổi**.

## 1. Quy tắc bắt buộc

1. **Không sửa `paper/main.tex`**, không sửa code trong `app/` (trừ khi Sang đồng ý). Chỉ sửa và thêm file trong `NCKH/experiments/`.
2. **Cố định cấu hình suốt đợt đo**: cùng một commit, cùng `.env`, cùng giọng đọc. Ghi tất cả vào `NOTES.md`.
3. **Không trộn số cũ và số mới** trong cùng một bảng hay một phương án. Số cũ chỉ để tham chiếu và phải ghi rõ "bản `e5a8cb7`".
4. **Server**: được build lại 3 container ai (`ai-api`, `ai-worker`, `ai-beat`) và chạy script đo trong `lms_ai_worker`. **Không đụng** DB schema, volume, `backend`, `frontend`. Chỉ đọc DB bằng SELECT. Xóa dữ liệu (bản lồng tiếng cũ của 4 bài thử nghiệm) chỉ khi ❓ Sang đồng ý.
5. **Bí mật**: không in, không commit `.env`, token Modal, key Gemini/Azure/Groq. Kiểm tra env bằng `printenv TÊN_BIẾN` cụ thể, **không** `printenv` toàn bộ.
6. Không chọn lọc kết quả; lần chạy lỗi cũng ghi vào report kèm lý do.
7. Commit và push lên nhánh **`NCKH`** khi xong, rồi nhắn Sang.

## 2. Thông tin cần hỏi trước (❓ hỏi người dùng)

- ❓ Đã merge `develop` mới nhất (có commit `c82339e` trở về sau) vào nhánh deploy trên server chưa? Server đang ở thư mục nào (`/var/lms/ai-worker`, `/var/lms/be`)?
- ❓ `.env` trên server đã có `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` đúng tài khoản đã deploy hàm `lms-demucs` bản mới (commit `34052fb`) chưa? (Chỉ hỏi "đã có chưa".)
- ❓ Credit Gemini còn bao nhiêu? Đợt đo ước khoảng 20–40K₫ (bản mới gọi LLM ít hơn nhiều so với 286 lời gọi của bản cũ).
- ❓ Có cho phép xóa bản lồng tiếng và transcript cũ của 4 bài trong khóa 92 (lesson 2284, 2285, 2286, 2288) để đo lại "lần lồng tiếng đầu" không?
- ❓ Có đang có job lồng tiếng thật nào chạy không (để không build/restart giữa chừng)?

## 3. Bước A — Build lại môi trường trên server

> Server có thể còn image, container và `.env` của đợt trước (3.5 Flash, không có `modal`, FFmpeg 5.1).
> **Phải build lại**, không chỉ `restart`.

```bash
# A0. Ghi lại trạng thái cũ (dán vào NOTES)
docker exec lms_ai_worker sh -c "ffmpeg -version | head -1; cat /etc/debian_version"
docker exec lms_ai_worker printenv GEMINI_MODEL DUBBING_THINKING_LEVEL BGM_SEPARATION
cd /var/lms/ai-worker && git log --oneline -1

# A1. Lấy code mới (nhánh đang deploy, ví dụ develop)
cd /var/lms/ai-worker && git pull
git log --oneline -1                                   # ghi commit này vào NOTES
grep -c "place_on_timeline_ffmpeg" app/audio_utils.py   # phải > 0
grep -c "prefetch" app/services/dubbing_service.py      # phải > 0 (dây chuyền chunk)
```

**A2. Sửa `.env` của ai-worker trên server** (mở bằng trình soạn thảo, không `cat` ra màn hình):

| Biến | Giá trị |
|---|---|
| `GEMINI_MODEL` | `gemini-3.6-flash` |
| `GEMINI_MODELS` | **để trống** (không có model dự phòng, để mọi câu dùng cùng một model) |
| `DUBBING_THINKING_LEVEL` | `minimal` |
| `BGM_SEPARATION` | `modal` (giữ nhạc nền **bật**, theo quyết định của Sang) |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | token đúng tài khoản deploy `lms-demucs` |
| `TIMELINE_ENGINE` | `ffmpeg` (mặc định, có thể không đặt) |
| `CHUNK_MINUTES` | `10` |
| `MAX_RESUMMARIZE_ATTEMPTS` | `2` |
| `MIN_RESUMMARIZE_FRAME_SEC` | `2.0` (mặc định) |

```bash
# A3. Build lại từ base image mới, tạo lại container để nạp .env mới
cd /var/lms/be            # thư mục chứa docker-compose.yml
docker compose build --pull --no-cache ai-api ai-worker ai-beat
docker compose up -d --force-recreate --no-deps ai-api ai-worker ai-beat

# A4. Kiểm tra (dán kết quả vào NOTES)
docker exec lms_ai_worker sh -c "ffmpeg -version | head -1; cat /etc/debian_version"   # ffmpeg 7.x, Debian 13.x
docker exec lms_ai_worker printenv GEMINI_MODEL DUBBING_THINKING_LEVEL BGM_SEPARATION   # gemini-3.6-flash / minimal / modal
docker exec lms_ai_worker python -c "from app.config import settings as s; print(s.timeline_engine, s.bgm_separation, s.chunk_minutes, s.max_resummarize_attempts, s.min_resummarize_frame_sec, s.tts_concurrency)"
docker exec lms_ai_worker python -c "import modal; modal.Function.from_name('lms-demucs','separate').hydrate(); print('modal ok')"
docker inspect -f '{{.State.Status}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' lms_ai_worker
```

- Giữ cấu hình log (`max-size 10m`, `max-file 3`) và `--reload-exclude "NCKH/experiments/*"` đã thêm ngày 13/11 trong `docker-compose.yml`. Nếu bị mất sau khi pull, thêm lại và ghi vào NOTES.
- **Lưu ý:** `restart` **không** nạp lại `.env`; phải `up -d --force-recreate`.
- Nếu một bước kiểm tra sai: dừng lại, ghi lỗi vào report, ❓ hỏi Sang.

**A5. Ghi lại trạng thái tốc độ đọc của giọng** (ảnh hưởng `max_chars`):
```bash
docker exec lms_redis redis-cli --scan --pattern 'dubbing:tts_cps:*'
docker exec lms_redis redis-cli get 'dubbing:tts_cps:vi-VN-HoaiMyNeural'
docker exec lms_redis redis-cli get 'dubbing:tts_cps:vi-VN-NamMinhNeural'
```
Ghi giá trị vào NOTES. **Không xóa** các khóa này nếu chưa ❓ hỏi Sang (xem mục B, V4 lần 1/lần 2).

## 4. Bước B — Sửa script đo cho khớp pipeline mới

`NCKH/experiments/run_experiment.py` **đang chạy LỖI trên code mới**:
- gọi `translation._build_adapt_prompt` (đã bị gỡ);
- V3 tăng tốc bằng tham số `rate=` của `azure_tts.synthesize` (SSML, pipeline không còn dùng);
- bộ đếm vá `translation.resummarize`, trong khi pipeline gọi `translation.resummarize_batch`.

Sửa (hoặc tạo `run_experiment_v2.py`, giữ nguyên bản cũ để tái lập số cũ) theo định nghĩa phương án **đã ghi trong `main.tex`**:

| PA | Dịch | Tăng tốc | Rút gọn | Cách gọi |
|---|---|---|---|---|
| **V1** | không ràng buộc độ dài: `translation._build_direct_prompt` + `gemini.generate` | không | không | TTS 1 lần, câu ngắn hơn khung coi `t_final = t_orig` |
| **V2** | `translation.translate_batch(segments, src, tgt, max_chars=None)` (chỉ ngân sách thời lượng) | không | không | như V1 |
| **V3** | `translate_batch` **có** `max_chars = max(4, int(cps × T_orig × 1,15))` (cps đọc từ Redis như pipeline; nếu chưa có thì ghi rõ và dùng `None`) | `audio_utils.change_tempo(path, min(R, 1,3))` | **không** | TTS 1 lần rồi atempo |
| **V4** | như V3 | như pipeline | như pipeline | gọi thẳng `dubbing_service._synthesize_segments(segments, texts, voice, out_paths, tgt)` cho **cả chunk** |

Yêu cầu khác:
- **V3 và V4 dùng chung một kết quả dịch** (cùng một lời gọi `translate_batch` có `max_chars`), giống cách đợt trước V2–V4 dùng chung bản dịch. Như vậy khác biệt giữa V3 và V4 chỉ còn là bước rút gọn.
- **Mốc câu** dùng đúng như pipeline: ASR qua `groq_asr.transcribe` (đã lấy mốc theo từ đầu tiên) rồi `dubbing_service.clamp_stt_segments`. **Không dùng lại `asr_cache.json` cũ** (mốc cũ là mốc đầu đoạn): xóa hoặc đổi tên thư mục `.cache/` trước khi chạy để ASR chạy lại.
- Câu chỉ có dấu câu: xử lý như pipeline (`dubbing_service._has_speakable_text`), ghi số câu bị bỏ.
- Đếm lời gọi bằng cách vá `gemini.generate` (đếm tất cả lời gọi LLM, kể cả dịch lại câu bị bỏ sót) và `azure_tts.synthesize`; đếm riêng số lời gọi `resummarize_batch` và **số câu** được rút gọn.
- Ghi `t_final` sau atempo: `max(độ dài file, t_orig)`, giống cách tính cũ. `applied_rate` = hệ số atempo.
- `run_meta.json` ghi thêm: `gemini_model`, `dubbing_thinking_level`, `bgm_separation`, `tts_concurrency`, giá trị `tts_cps` của từng giọng **trước** và **sau** khi chạy, commit.
- Chạy thử `--max-chunks 1 --only lec01` trước, kiểm tra không lỗi, rồi mới chạy đủ.
- `check_full_length.py` phải ghép bằng **đúng hàm của pipeline hiện tại** (`audio_utils.place_on_timeline_ffmpeg` nếu `TIMELINE_ENGINE=ffmpeg`), mốc `b_i` lấy từ ASR mới.

## 5. Bước C — Đo

> Tất cả chạy trong `lms_ai_worker` trên server, cùng commit ở A1, như đợt trước:
> `docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/...`

| # | Việc | Lệnh / cách làm | Số liệu cho bảng nào |
|---|---|---|---|
| C1 | **V1–V4** trên 4 bài (`videos.json`), toàn bộ độ dài, giữ audio | `run_experiment_v2.py --manifest NCKH/experiments/videos.json --run-id v3_r1 --keep-audio` rồi `analyze.py results/v3_r1` | Bảng 2 |
| C2 | **V4 lần 2** (đã có `tts_cps` sau C1) | `--variants V4 --run-id v3_r2` | Bảng 2: báo **cả 2 lần** V4; Sang chọn lần chính |
| C3 | **Độ trễ theo trục thời gian** | `check_full_length.py results/v3_r1 --variants V2,V4 --assembly new` và `drift_analysis.py` | Bảng 3 (dòng (c) mới) |
| C4 | ❓ **4 job thật qua web** (lần lồng tiếng đầu, có ASR và tách nhạc): xóa bản lồng tiếng + transcript cũ của 4 lesson (nếu Sang cho phép), bấm lồng tiếng `vi-VN` từng bài, **chạy tuần tự từng bài** (không chạy song song với C1–C2) | Lấy số từ `server_job_stats.py` / `server_job_stats_ext.sql` + log `docker logs lms_ai_worker 2>&1 \| grep TIMING` | Bảng 4 |
| C5 | **L4**: chọn 50 câu rút gọn mới của V4 (`sample_fidelity.py results/v3_r1 --n 50 --seed 42 --min-frame 2.0 --baseline V3`; dùng **V3** làm bản dịch đầy đủ vì đó là đúng văn bản V4 nhận trước khi rút gọn), tạo file chấm có cột câu gốc EN, bản dịch đầy đủ trước rút gọn, bản rút gọn, **không có điểm** | Gửi file cho **Sang và Thiện chấm độc lập**, sau đó thống nhất câu lệch (như lần trước) | Đoạn L4 |

Với C4, mỗi job ghi: thời lượng bài, số chunk, `processing_sec`, `first_chunk_sec`, thời gian giữa các chunk, trạng thái, số lần thử lại, và các dòng `TIMING` (asr, dịch, chờ chunk trước, tts, ghép, nhạc, tải lên). Bài > 10 phút (lec02, lec03, lec04) có nhiều chunk: kiểm tra dây chuyền chạy (có `cho_chunk_truoc` trong log).

## 6. Đầu ra — REPORT để Sang kiểm tra

Tạo `NCKH/experiments/reports/REPORT_<yyyymmdd>_<tên>.md` theo **mẫu ở `HUONG_DAN_NHOM.md` mục 9.6**, bổ sung:
- Mục **Môi trường**: kết quả các lệnh A0, A4, A5 (trước/sau build), commit, model, thinking, nhạc nền, `tts_cps`.
- Bảng V1–V4 của `v3_r1`, dòng V4 của `v3_r2`, và **một dòng tham chiếu "bản cũ e5a8cb7"** lấy từ `results/post_fix_r1/summary.json` (ghi rõ là số cũ).
- Bảng độ trễ theo trục thời gian (cũ và mới, ghi rõ nguồn).
- Bảng 4 job thật: số mới cạnh số cũ (`results/server_20261113`).
- Số câu L4 đã chọn và đường dẫn file chấm.
- Phần **Bất thường**: ví dụ R rất lớn, câu bị bỏ sót khi dịch, chunk rơi về tăng tốc tối đa do rút gọn lỗi, log `HET CREDIT (402)`, lần tách nhạc lỗi.
- Phần **Cách kiểm tra lại**: lệnh tái tạo từng con số.

Lưu kết quả ở `NCKH/experiments/results/v3_r1/`, `v3_r2/`, `server_<ngày>/`. **Không commit** `audio/`, `.cache/`, `media/`, video.

## 7. Checklist trước khi nhắn Sang

- [ ] `printenv` trong container ra `gemini-3.6-flash`, `minimal`, `modal`; ghi vào NOTES.
- [ ] Mọi lần chạy dùng cùng commit; commit có trong NOTES.
- [ ] ASR đã chạy lại (không dùng `asr_cache.json` cũ).
- [ ] Số trong REPORT truy được về file trong `results/`.
- [ ] Không sửa `paper/main.tex`, không commit bí mật.
- [ ] Đã push nhánh `NCKH`.
