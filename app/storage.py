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

from app.config import settings

_client = None


def _region_from_endpoint(endpoint: str) -> str:
    # Vd: s3.us-east-005.backblazeb2.com -> us-east-005 (khớp B2Config.java phía be)
    match = re.search(r"s3\.([a-z0-9-]+)\.backblazeb2\.com", endpoint)
    return match.group(1) if match else "us-east-005"


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
