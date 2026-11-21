"""M2 — tách giọng / nhạc nền bằng Demucs trên GPU của Modal (deploy 1 lần, worker gọi từ xa).

Deploy:  py -m modal deploy modal_apps/demucs_separator.py
Thử:     py -m modal run modal_apps/demucs_separator.py --input <file audio>

Worker (`app/services/background_music.py`) gọi `modal.Function.from_name(APP_NAME, "separate")`.
Image của worker KHÔNG cần PyTorch/Demucs — toàn bộ chạy trên Modal, chỉ tính tiền theo giây GPU.
"""

import os
import time
from pathlib import Path

import modal

APP_NAME = "lms-demucs"
app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("torch==2.1.2", "torchaudio==2.1.2", "demucs==4.0.1", "numpy<2")
    # Tải sẵn trọng số vào image: lúc chạy không phải tải lại (giảm thời gian khởi động).
    .run_commands("python -c \"from demucs.pretrained import get_model; get_model('htdemucs')\"")
)


# Modal chỉ cho chạy GPU khi tài khoản đã thêm phương thức thanh toán (vẫn trừ vào $30 miễn phí/tháng).
# Chưa có thẻ: deploy với DEMUCS_GPU=none -> chạy CPU 8 nhân (chậm hơn, đủ để thử chất lượng tách).
_GPU = os.environ.get("DEMUCS_GPU", "T4")
_RESOURCES = {"cpu": 8.0, "memory": 8192} if _GPU.lower() == "none" else {"gpu": _GPU}


@app.function(image=image, timeout=1800, **_RESOURCES)
def separate(audio: bytes, suffix: str = ".mp3") -> dict:
    """Trả {"music": mp3 bytes (không có giọng), "vocals": mp3 bytes, "separate_sec": float}."""
    import subprocess
    import tempfile

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{suffix}"
        src.write_bytes(audio)
        subprocess.run(
            ["python", "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "--mp3", "-o", tmp, str(src)],
            check=True, capture_output=True,
        )
        out = Path(tmp) / "htdemucs" / "in"
        return {
            "music": (out / "no_vocals.mp3").read_bytes(),
            "vocals": (out / "vocals.mp3").read_bytes(),
            "separate_sec": round(time.time() - t0, 1),
        }


@app.local_entrypoint()
def main(input: str):
    src = Path(input)
    t0 = time.time()
    result = separate.remote(src.read_bytes(), src.suffix)
    (src.parent / f"{src.stem}_music.mp3").write_bytes(result["music"])
    (src.parent / f"{src.stem}_vocals.mp3").write_bytes(result["vocals"])
    print(f"tach tren GPU {result['separate_sec']} s | tong {round(time.time() - t0, 1)} s")
