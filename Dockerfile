# =====================================================================
# AI Worker dev image — FastAPI + Celery (Python 3.11)
#
# Image GỌN: chỉ cài requirements-app.txt (fastapi, celery, httpx…),
# KHÔNG cài torch/whisperx/demucs của VideoLingo.
#
# Lý do: §5.1.1 của KLTN chọn Groq Cloud API cho STT nên không cần GPU
# ⇒ image ~400 MB thay vì ~8 GB, dev workstation chỉ cần 40 GB đĩa.
# Muốn chạy WhisperX local để đo đối chứng (Chương 6) thì dùng
# Dockerfile.whisperx.
#
# Cùng một image dùng cho 3 service, khác nhau ở `command`:
#   ai-api    → uvicorn app.main:app
#   ai-worker → celery worker
#   ai-beat   → celery beat
# =====================================================================
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg: BẮT BUỘC — tách audio, cắt chunk 10 phút, ghép final.mp3
#         (BR-CHUNK-02, BR-CHUNK-05)
# curl:   healthcheck + cài Deno bên dưới
# unzip:  script cài Deno cần để giải nén bản tải về
# libasound2, libssl3, ca-certificates: Giai đoạn 11 (F11.3) — azure-cognitiveservices-speech
#         là native binding (không thuần Python), cần các thư viện hệ thống này để import được
#         (xác nhận theo tài liệu cài đặt chính thức của Azure Speech SDK cho Linux)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl unzip libasound2 libssl3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno: yt-dlp cần một JS runtime để giải mã chữ ký (nsig) khi tải audio YouTube
# (BR-CHUNK-01) — thiếu runtime này yt-dlp mất một số định dạng hoặc dễ bị 403 dù
# bản thân yt-dlp đã mới nhất (xem app/media.py::download_youtube_audio). Tải thẳng
# file nhị phân từ GitHub Releases (KHÔNG dùng script cài chính thức deno.land/install.sh
# — bước phụ của nó tải cấu hình shell completion từ registry JSR riêng, hay lỗi 403
# không liên quan gì tới YouTube, làm cả build thất bại dù bản thân deno đã tải xong).
RUN curl -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip \
    && unzip -o /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && chmod +x /usr/local/bin/deno \
    && deno --version

# Cài dependency trước để cache layer
COPY requirements-app.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir --upgrade -r requirements-app.txt

COPY . .

# Thư mục file trung gian — docker-compose mount volume ai_tmp_storage vào đây.
# Nội dung phải được dọn sau mỗi job, tối đa 24 giờ (BR-STORAGE-01).
RUN mkdir -p /tmp/lms-processing

EXPOSE 8000

# Mặc định chạy API; docker-compose override cho worker và beat
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
