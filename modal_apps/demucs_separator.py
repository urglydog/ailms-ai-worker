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


_MODEL = None   # model Demucs nạp 1 lần cho mỗi container (container được giữ ấm giữa các lời gọi)


def _model():
    """Nạp `htdemucs` lên GPU đúng 1 lần cho mỗi container (22/11/2026).

    Trước đây mỗi lời gọi chạy CLI `python -m demucs` -> khởi động Python + nạp model lại từ đầu
    (~3–5 s/lời gọi). Giờ lời gọi "đánh thức" đã nạp sẵn, các phần audio gửi tới chỉ còn chạy model.
    """
    global _MODEL
    if _MODEL is None:
        import torch
        from demucs.pretrained import get_model

        model = get_model("htdemucs")
        model.eval()
        if torch.cuda.is_available():
            model.cuda()
        _MODEL = model
    return _MODEL


def _separate_in_process(src: Path, out_dir: Path) -> tuple[Path, Path]:
    """Đúng các bước của CLI `demucs --two-stems=vocals --mp3` (demucs 4.0.1, mặc định shifts=1,
    overlap=0.25, clip='rescale') nhưng dùng model đã nạp sẵn; MP3 xuất ra nhẹ hơn (xem dưới)."""
    import torch
    from demucs.apply import apply_model
    from demucs.audio import save_audio
    from demucs.separate import load_track

    model = _model()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    wav = load_track(src, model.audio_channels, model.samplerate)
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / ref.std()
    with torch.no_grad():
        sources = apply_model(model, wav[None], device=device, shifts=1, split=True, overlap=0.25, progress=False)[0]
    sources = sources * ref.std() + ref.mean()
    idx = model.sources.index("vocals")
    vocals = sources[idx]
    music = sources.sum(0) - vocals
    vocals_path, music_path = out_dir / "vocals.mp3", out_dir / "no_vocals.mp3"
    # 320 kbps như CLI làm mỗi phần trả về ~2 x 2,4 MB/phút -> tải về chậm. Nhạc được trộn lại ở 96 kbps,
    # giọng gốc chỉ dùng để ĐO độ to -> 192 / 96 kbps là dư (22/11/2026).
    save_audio(vocals.cpu(), str(vocals_path), samplerate=model.samplerate, bitrate=96, clip="rescale")
    save_audio(music.cpu(), str(music_path), samplerate=model.samplerate, bitrate=192, clip="rescale")
    return music_path, vocals_path


@app.function(image=image, timeout=1800, **_RESOURCES)
def separate(audio: bytes, suffix: str = ".mp3") -> dict:
    """Trả {"music": mp3 bytes (không có giọng), "vocals": mp3 bytes, "separate_sec": float}.

    `audio` rỗng = lời gọi "đánh thức" (worker gọi ngay đầu job): container GPU khởi động sẵn VÀ nạp
    model lên GPU, trả về ngay, không chạy Demucs.
    """
    import subprocess
    import tempfile

    if not audio:
        t0 = time.time()
        _model()
        return {"warm": True, "load_sec": round(time.time() - t0, 1)}

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{suffix}"
        src.write_bytes(audio)
        try:
            music_path, vocals_path = _separate_in_process(src, Path(tmp))
            mode = "in_process"
        except Exception as exc:  # dự phòng: chạy CLI như cũ
            print(f"Tach trong tien trinh loi, dung CLI: {exc}")
            subprocess.run(
                ["python", "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "--mp3", "-o", tmp, str(src)],
                check=True, capture_output=True,
            )
            out = Path(tmp) / "htdemucs" / "in"
            music_path, vocals_path = out / "no_vocals.mp3", out / "vocals.mp3"
            mode = "cli"
        return {
            "music": music_path.read_bytes(),
            "vocals": vocals_path.read_bytes(),
            "separate_sec": round(time.time() - t0, 1),
            "mode": mode,
        }


@app.local_entrypoint()
def main(input: str):
    src = Path(input)
    t0 = time.time()
    result = separate.remote(src.read_bytes(), src.suffix)
    (src.parent / f"{src.stem}_music.mp3").write_bytes(result["music"])
    (src.parent / f"{src.stem}_vocals.mp3").write_bytes(result["vocals"])
    print(f"tach tren GPU {result['separate_sec']} s | tong {round(time.time() - t0, 1)} s")
