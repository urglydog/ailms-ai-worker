"""Upload file lên Backblaze B2 (tương thích S3) — bản Python song song với
`com.lms.common.storage.B2StorageService` phía backend. AI Worker tự upload trực
tiếp (không qua backend) vì đây là bí mật hạ tầng dùng chung, xem
`project/ai-worker/.env` mục B2_*.

`boto3` tự nó đồng bộ nên bọc bằng `asyncio.to_thread()` để không chặn event loop.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings

_client = None


def _region_from_endpoint(endpoint: str) -> str:
    # Vd: s3.us-east-005.backblazeb2.com -> us-east-005 (khớp B2Config.java phía be)
    match = re.search(r"s3\.([a-z0-9-]+)\.backblazeb2\.com", endpoint)
    return match.group(1) if match else "us-east-005"


def _client_config() -> BotoConfig:
    """Thời gian chờ ngắn + thử lại nhiều lần (22/11/2026).

    Mặc định boto3 chờ 60 s mỗi lần kết nối/đọc bị treo rồi mới thử lại: đo được upload chunk
    7 MB lên B2 mất 182 s (job 46, ≈ 3 × 60 s) trong khi bình thường chỉ 2–9 s. Treo = không có
    byte nào đi/về trong suốt khoảng chờ (mạng chậm nhưng vẫn chạy thì KHÔNG bị cắt), nên chờ
    ngắn lại không làm hỏng upload chậm; một lần treo giờ chỉ tốn ~`B2_READ_TIMEOUT_SEC` giây.
    """
    return BotoConfig(
        connect_timeout=settings.b2_connect_timeout_sec,
        read_timeout=settings.b2_read_timeout_sec,
        retries={"max_attempts": settings.b2_max_attempts, "mode": "standard"},
    )


def _get_client():
    global _client
    if _client is None:
        endpoint = settings.b2_endpoint
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{endpoint}",
            aws_access_key_id=settings.b2_key_id,
            aws_secret_access_key=settings.b2_application_key,
            region_name=_region_from_endpoint(endpoint),
            config=_client_config(),
        )
    return _client


async def upload_file(local_path: str | Path, key: str, *, content_type: str = "audio/mpeg") -> str:
    """Upload 1 file lên B2, trả về URL công khai để lưu vào `AudioChunk.fileUrl` /
    `AudioTrack.finalUrl`.
    """
    def _upload() -> str:
        client = _get_client()
        client.upload_file(
            str(local_path),
            settings.b2_bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return f"https://{settings.b2_endpoint}/{settings.b2_bucket_name}/{key}"

    return await asyncio.to_thread(_upload)


def public_url(key: str) -> str:
    """URL công khai của 1 object — cùng định dạng `upload_file` trả về."""
    return f"https://{settings.b2_endpoint}/{settings.b2_bucket_name}/{key}"


async def exists(key: str) -> bool:
    """Object đã có trên B2 chưa (HEAD, không tải nội dung). Lỗi mạng/quyền -> coi như chưa có."""
    def _head() -> bool:
        try:
            _get_client().head_object(Bucket=settings.b2_bucket_name, Key=key)
            return True
        except Exception:
            return False

    return await asyncio.to_thread(_head)


async def download_file(key: str, local_path: str | Path) -> bool:
    """Tải 1 object từ B2 về file. Trả False nếu object chưa có (hoặc tải lỗi) — dùng làm cache."""
    def _download() -> bool:
        try:
            _get_client().download_file(settings.b2_bucket_name, key, str(local_path))
            return Path(local_path).stat().st_size > 0
        except Exception:
            Path(local_path).unlink(missing_ok=True)
            return False

    return await asyncio.to_thread(_download)
