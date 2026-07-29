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
# curl:   healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Cài dependency trước để cache layer
COPY requirements-app.txt .
RUN pip install --upgrade pip && pip install -r requirements-app.txt

COPY . .

# Thư mục file trung gian — docker-compose mount volume ai_tmp_storage vào đây.
# Nội dung phải được dọn sau mỗi job, tối đa 24 giờ (BR-STORAGE-01).
RUN mkdir -p /tmp/lms-processing

EXPOSE 8000

# Mặc định chạy API; docker-compose override cho worker và beat
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
