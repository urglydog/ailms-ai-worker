# ailms-ai-worker — AI Service

Dịch vụ AI của **AI-Powered LMS**. Python 3.11 · FastAPI · Celery · Redis.

> **Chạy hệ thống:** xem **`../be/RUNNING.md`** (docker-compose nằm ở repo `be`).

## Vai trò trong kiến trúc

Đây là **Service 2** của kiến trúc Dịch vụ kép: xử lý tác vụ CPU/GPU-bound, nặng về
đa phương tiện.

> ⚠️ **Service này KHÔNG kết nối MySQL trực tiếp.** Mọi thay đổi dữ liệu nghiệp vụ
> phải gọi callback về backend (`INTERNAL_BE_URL`). Đây là ranh giới kiến trúc, không
> phải sở thích — xem `Skills/CodeSkills/05_AIPoweredLMS/ai-agent/context/architecture.md`.

Chạy 3 tiến trình từ **cùng một image**, khác nhau ở `command`:

| Service | Lệnh | Việc |
| --- | --- | --- |
| `ai-api` | `uvicorn app.main:app` | UC30 Socratic Tutor, UC49 Course Discovery (HTTP đồng bộ) |
| `ai-worker` | `celery ... worker` | UC19 pipeline lồng tiếng, UC25 sinh học liệu |
| `ai-beat` | `celery ... beat` | Tác vụ định kỳ (BR-STORAGE-01, BR-NOTIFY-01, BR-DUB-08) |

## Cấu trúc

```
app/
├─ main.py            FastAPI + lifespan (đóng provider client khi shutdown)
├─ celery_app.py      Celery + beat_schedule 4 tác vụ định kỳ
├─ config.py          pydantic-settings, đọc toàn bộ từ env
├─ api/               Router mỏng ≤10 dòng: health, tutor, discovery
├─ services/          Logic nghiệp vụ (điền dần theo giai đoạn)
├─ providers/         base, groq_asr, gemini, edge_tts
└─ tasks/             dubbing, material, maintenance
core/                 VideoLingo upstream — thư viện thuật toán, chỉ import
```

## 4 tầng và ranh giới import

| Tầng | Được import | KHÔNG được import |
| --- | --- | --- |
| `api/` | `services/`, schema Pydantic | `httpx`, `providers/` |
| `services/` | `providers/` | `httpx` trực tiếp, `HTTPException` |
| `providers/` | `httpx` | `services/` |
| `tasks/` | `services/` | `httpx` trực tiếp |

## Provider — hai nguyên tắc

**1. Bulkhead.** Mỗi provider có `httpx.AsyncClient` **riêng** với timeout/limits
riêng. Gemini phản hồi chậm không được làm cạn connection pool mà Edge-TTS đang cần.

**2. Anti-corruption layer.** Provider trả **dataclass** hoặc raise `ProviderError`
có cờ `retryable` — tuyệt đối không trả `dict` thô. Nhờ đó tầng retry (BR-CHUNK-04,
tối đa 3 lần exponential backoff) quyết định được mà không cần biết nội bộ của
Groq/Gemini/Edge-TTS.

## STT: Groq mặc định, WhisperX là phương án đối chứng

| | Mặc định | Đối chứng |
| --- | --- | --- |
| Backend | Groq Cloud API `whisper-large-v3-turbo` | WhisperX local |
| Dockerfile | `Dockerfile` (~400 MB) | `Dockerfile.whisperx` (~6–8 GB, cần GPU) |
| Biến env | `ASR_BACKEND=groq` | `ASR_BACKEND=whisperx_local` |
| Lý do | §5.1.1 KLTN: *"triệt tiêu phụ thuộc GPU đắt đỏ tại Local"* | Đo độ chính xác mốc thời gian cho §6.3.2 |

⚠️ **Việc cần làm đầu Giai đoạn 5:** BR-DUB-01 trong KLTN mô tả WhisperX với forced
alignment `wav2vec2`, còn Groq trả word-level timestamp từ API. Mốc thời gian ảnh
hưởng trực tiếp tới BR-DUB-03 (tính `T_orig`) và BR-TUTOR-02 (trích dẫn nhấp được),
nên **phải đo đối chứng trên một video thật trước khi chốt**.

## VideoLingo upstream

`core/` là source của [VideoLingo](https://github.com/Huanshere/VideoLingo), giữ làm
**thư viện thuật toán** (`READMEVideoLingo.md`, `LICENSE`, `requirements.txt`,
`config.yaml` là tài liệu tham chiếu). Phần Streamlit, installer và docs đã dọn.

Bảng dùng/bỏ từng bước trong pipeline 12 bước: `doc/DEVELOPMENT_PLAN.md` mục 1.

> 🚫 **Tuyệt đối không dùng `core/_12_dub_to_vid.py`** (ghép audio vào video).
> Dual Player cần video gốc muted + `.mp3` **riêng**. Dùng bước 12 là phá vỡ toàn bộ
> kiến trúc UC16.

> ⚠️ `core/` đọc state từ `config.yaml` toàn cục và ghi filesystem cố định nên
> **không chạy song song nhiều job được**. Khi port sang `app/`, mọi tham số phải
> truyền qua đối số hàm.

## Đặc tả nghiệp vụ

| Cần gì | Đọc |
| --- | --- |
| Pipeline lồng tiếng đầy đủ | `Skills/CodeSkills/05_AIPoweredLMS/skills/lms-dubbing-pipeline/` |
| 4 tác tử AI | `.../skills/lms-multi-agent/` |
| Quy chuẩn code | `Skills/CodeSkills/04_TechStack/rules/lms/lms-ai-worker-pipeline.md` |

Kế hoạch 11 giai đoạn: `doc/DEVELOPMENT_PLAN.md`.
