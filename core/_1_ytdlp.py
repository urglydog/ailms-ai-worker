import os,sys
import glob
import json
import random
import re
import subprocess
from core.utils import *

OUTPUT_DIR = "output"
INPUT_MANIFEST = "input_manifest.json"
GENERATED_AUDIO_NAMES = {"dub.mp3", "normalized_dub.wav"}


def _load_proxy_list() -> list[str]:
    """BUG THẬT (05/09/2026) — xem docstring `_download_with_proxy_rotation` bên dưới để biết vì
    sao cần proxy dân dụng thay vì gọi thẳng. Đọc `secrets/youtube_proxies.txt` (đường dẫn khai ở
    `config.yaml` → `youtube.proxy_list_path`), MỖI DÒNG 1 proxy, chấp nhận 2 dạng để không phụ
    thuộc 1 nhà cung cấp cụ thể:
      - URL đầy đủ: `http://user:pass@host:port` (DataImpulse và đa số nhà cung cấp residential
        hiện đại — thường chỉ 1 dòng, 1 cổng gateway duy nhất tự luân chuyển IP phía sau).
      - `host:port:user:pass` (Webshare và vài nhà cung cấp cũ xuất theo dòng, nhiều IP cố định).
    File không tồn tại hoặc rỗng → trả về `[]`, `download_video_ytdlp` tự hiểu là "không dùng
    proxy", tải thẳng như trước đây — không bắt buộc phải có proxy mới chạy được.
    """
    proxy_list_path = load_key("youtube.proxy_list_path")
    if not proxy_list_path or not os.path.exists(proxy_list_path):
        return []
    proxies = []
    with open(proxy_list_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "://" in line:
                proxies.append(line)
                continue
            parts = line.split(":")
            if len(parts) == 4:
                host, port, user, password = parts
                proxies.append(f"http://{user}:{password}@{host}:{port}")
            else:
                rprint(f"[yellow]Bo qua dong proxy khong dung dinh dang: {line}[/yellow]")
    return proxies


def _download_with_proxy_rotation(YoutubeDL, base_opts: dict, url: str, proxies: list[str]) -> None:
    """BUG THẬT (05/09/2026): yt-dlp bị YouTube chặn ("Sign in to confirm you're not a bot") khi
    tải trực tiếp từ IP datacenter/VPS. Đã XÁC NHẬN THẬT 10 proxy MIỄN PHÍ dạng datacenter (dùng
    chung, dễ bị liệt sẵn vào blacklist) KHÔNG giải quyết được — vẫn bị chặn y hệt trên cả 4/4
    proxy đã thử, có lúc còn kèm 429 Too Many Requests. Chỉ proxy RESIDENTIAL thật (trả phí, IP
    trông như 1 kết nối Internet nhà dân) mới có tác dụng thật sự.

    Thử LẦN LƯỢT các proxy theo thứ tự XÁO TRỘN ngẫu nhiên (dàn tải qua nhiều IP thay vì luôn đi
    cùng 1 IP mỗi lần — giảm khả năng chính IP đó bị chặn dần theo thời gian), dùng proxy tiếp
    theo nếu cái trước lỗi. Chỉ ném lỗi thật khi TẤT CẢ proxy trong danh sách đều thất bại — với
    nhà cung cấp kiểu DataImpulse (1 gateway duy nhất) danh sách chỉ có 1 phần tử, vòng lặp coi
    như thử đúng 1 lần, không có gì khác biệt so với gọi thẳng.
    """
    shuffled = proxies[:]
    random.shuffle(shuffled)
    last_error: Exception | None = None
    for proxy in shuffled:
        attempt_opts = {**base_opts, "proxy": proxy}
        try:
            with YoutubeDL(attempt_opts) as ydl:
                ydl.download([url])
            return
        except Exception as e:
            last_error = e
            rprint(f"[yellow]Proxy loi, thu proxy khac (con {len(shuffled) - shuffled.index(proxy) - 1}): {e}[/yellow]")
    if last_error is not None:
        raise last_error

def sanitize_filename(filename):
    # Remove or replace illegal characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Ensure filename doesn't start or end with a dot or space
    filename = filename.strip('. ')
    # Use default name if filename is empty
    return filename if filename else 'video'

def update_ytdlp():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
        if 'yt_dlp' in sys.modules:
            del sys.modules['yt_dlp']
        rprint("[green]yt-dlp updated[/green]")
    except subprocess.CalledProcessError as e:
        rprint("[yellow]Warning: Failed to update yt-dlp: {e}[/yellow]")
    from yt_dlp import YoutubeDL
    return YoutubeDL

def download_video_ytdlp(url, save_path='output', resolution='1080'):
    os.makedirs(save_path, exist_ok=True)
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best' if resolution == 'best' else f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]',
        'outtmpl': f'{save_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'writethumbnail': True,
        'merge_output_format': 'mp4',
        'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}],
    }

    # Read Youtube Cookie File
    cookies_path = load_key("youtube.cookies_path")
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = str(cookies_path)

    # Get YoutubeDL class after updating
    YoutubeDL = update_ytdlp()

    proxies = _load_proxy_list()
    if proxies:
        _download_with_proxy_rotation(YoutubeDL, ydl_opts, url, proxies)
    else:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    
    # Check and rename files after download
    for file in os.listdir(save_path):
        if os.path.isfile(os.path.join(save_path, file)):
            filename, ext = os.path.splitext(file)
            new_filename = sanitize_filename(filename)
            if new_filename != filename:
                os.rename(os.path.join(save_path, file), os.path.join(save_path, new_filename + ext))
    media_file = find_video_files(save_path)
    write_input_manifest(media_file, "video", save_path)

def write_input_manifest(media_file: str, media_type: str, save_path='output'):
    os.makedirs(save_path, exist_ok=True)
    manifest_path = os.path.join(save_path, INPUT_MANIFEST)
    media_path = media_file.replace("\\", "/") if sys.platform.startswith('win') else media_file
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"path": media_path, "type": media_type}, f, ensure_ascii=False, indent=2)

def _read_input_manifest(save_path='output'):
    manifest_path = os.path.join(save_path, INPUT_MANIFEST)
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    media_file = data.get("path")
    media_type = data.get("type")
    if media_type not in {"video", "audio"} or not media_file or not os.path.exists(media_file):
        return None
    return media_file.replace("\\", "/") if sys.platform.startswith('win') else media_file, media_type

def find_video_files(save_path='output'):
    video_files = [file for file in glob.glob(save_path + "/*") if os.path.splitext(file)[1][1:].lower() in load_key("allowed_video_formats")]
    # change \\ to /, this happen on windows
    if sys.platform.startswith('win'):
        video_files = [file.replace("\\", "/") for file in video_files]
    video_files = [file for file in video_files if not file.startswith("output/output")]
    if len(video_files) != 1:
        raise ValueError(f"Number of videos found {len(video_files)} is not unique. Please check.")
    return video_files[0]

def find_audio_files(save_path='output'):
    audio_files = [file for file in glob.glob(save_path + "/*") if os.path.splitext(file)[1][1:].lower() in load_key("allowed_audio_formats")]
    if sys.platform.startswith('win'):
        audio_files = [file.replace("\\", "/") for file in audio_files]
    audio_files = [file for file in audio_files if os.path.basename(file) not in GENERATED_AUDIO_NAMES]
    if len(audio_files) != 1:
        raise ValueError(f"Number of audio files found {len(audio_files)} is not unique. Please check.")
    return audio_files[0]

def _safe_find_video_file(save_path='output'):
    try:
        return find_video_files(save_path)
    except ValueError as e:
        if "found 0" in str(e):
            return None
        raise

def _safe_find_audio_file(save_path='output'):
    try:
        return find_audio_files(save_path)
    except ValueError as e:
        if "found 0" in str(e):
            return None
        raise

def find_media_file(save_path='output'):
    manifest = _read_input_manifest(save_path)
    if manifest:
        return manifest
    video_file = _safe_find_video_file(save_path)
    if video_file:
        return video_file, "video"
    audio_file = _safe_find_audio_file(save_path)
    if audio_file:
        return audio_file, "audio"
    raise ValueError("No media file found. Please download or upload a media file first.")

def is_audio_only_input(save_path='output'):
    # True when the input is a standalone audio file (no video present).
    # In this case VideoLingo only produces subtitle files; no video output.
    try:
        _, media_type = find_media_file(save_path)
        return media_type == "audio"
    except Exception:
        return False

if __name__ == '__main__':
    # Example usage
    url = input('Please enter the URL of the video you want to download: ')
    resolution = input('Please enter the desired resolution (360/480/720/1080, default 1080): ')
    resolution = int(resolution) if resolution.isdigit() else 1080
    download_video_ytdlp(url, resolution=resolution)
    print(f"🎥 Video has been downloaded to {find_video_files()}")
