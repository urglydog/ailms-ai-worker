"""M2 — trộn nhạc nền: lỗi/tắt thì giữ nguyên bản lồng tiếng, không làm hỏng job."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.services import background_music


def test_disabled_by_default_returns_no_task(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "bgm_separation", "")
    assert background_music.start_separation(tmp_path / "src.wav", tmp_path) is None


async def test_mix_skipped_without_task(tmp_path):
    assert await background_music.mix_into_chunk(tmp_path / "d.mp3", None, 0, 10, tmp_path) is False


async def test_failed_separation_keeps_dub(tmp_path):
    task = asyncio.create_task(asyncio.sleep(0, None))
    ffmpeg = AsyncMock()
    with patch("app.audio_utils._ffmpeg", ffmpeg):
        assert await background_music.mix_into_chunk(tmp_path / "d.mp3", task, 0, 10, tmp_path) is False
    ffmpeg.assert_not_awaited()


async def test_separation_error_is_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "bgm_separation", "modal")
    with patch("app.audio_utils._ffmpeg", AsyncMock(side_effect=RuntimeError("boom"))):
        task = background_music.start_separation(tmp_path / "src.wav", tmp_path)
        assert await task is None


async def test_mix_runs_ffmpeg_and_replaces_chunk(tmp_path):
    music = tmp_path / "bgm_music.mp3"
    music.write_bytes(b"m")
    dub = tmp_path / "d.mp3"
    dub.write_bytes(b"dub")

    async def fake_ffmpeg(*args):
        open(args[-1], "wb").write(b"mixed")

    task = asyncio.create_task(asyncio.sleep(0, music))
    with patch("app.audio_utils._ffmpeg", AsyncMock(side_effect=fake_ffmpeg)):
        assert await background_music.mix_into_chunk(dub, task, 0, 10, tmp_path) is True
    assert dub.read_bytes() == b"mixed"


def test_loudness_gain_matches_original_voice_and_is_clamped():
    assert background_music.loudness_gain_db(-24.0, -18.0) == 6.0      # long tieng nho hon goc 6 dB
    assert background_music.loudness_gain_db(-14.0, -20.0) == -6.0
    assert background_music.loudness_gain_db(-40.0, -10.0) == 12.0     # kep +12 dB
    assert background_music.loudness_gain_db(None, -18.0) == 0.0       # khong do duoc -> giu nguyen


async def test_mix_matches_loudness_and_keeps_music_level_without_ducking(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "bgm_ducking", False)
    monkeypatch.setattr(settings, "bgm_music_volume", 1.0)
    music = tmp_path / "bgm_music.mp3"
    music.write_bytes(b"m")
    (tmp_path / "bgm_vocals.mp3").write_bytes(b"v")
    dub = tmp_path / "d.mp3"
    dub.write_bytes(b"dub")
    calls = []

    async def fake_ffmpeg(*args):
        calls.append(args)
        open(args[-1], "wb").write(b"x")

    task = asyncio.create_task(asyncio.sleep(0, music))
    with patch("app.audio_utils._ffmpeg", AsyncMock(side_effect=fake_ffmpeg)), \
         patch("app.services.background_music.measure_loudness_lufs", AsyncMock(side_effect=[-24.0, -18.0])):
        assert await background_music.mix_into_chunk(dub, task, 0, 10, tmp_path) is True

    graph = calls[-1][calls[-1].index("-filter_complex") + 1]
    assert "volume=6.00dB" in graph           # giong long tieng duoc nang to bang giong goc
    assert "volume=1.0[mus]" in graph         # nhac giu nguyen am luong goc
    assert "sidechaincompress" not in graph   # mac dinh khong tu ha nhac


async def test_ducking_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "bgm_ducking", True)
    music = tmp_path / "bgm_music.mp3"
    music.write_bytes(b"m")
    dub = tmp_path / "d.mp3"
    dub.write_bytes(b"dub")
    calls = []

    async def fake_ffmpeg(*args):
        calls.append(args)
        open(args[-1], "wb").write(b"x")

    task = asyncio.create_task(asyncio.sleep(0, music))
    with patch("app.audio_utils._ffmpeg", AsyncMock(side_effect=fake_ffmpeg)):
        await background_music.mix_into_chunk(dub, task, 0, 10, tmp_path)
    assert "sidechaincompress" in calls[-1][calls[-1].index("-filter_complex") + 1]


def test_cache_prefix_depends_on_lesson_and_video():
    a = background_music.cache_prefix(7, "https://youtu.be/a")
    assert a.startswith("bgm/7/") and a != background_music.cache_prefix(7, "https://youtu.be/b")
    assert background_music.cache_prefix(None, "x") is None


async def test_cached_music_on_b2_skips_gpu(tmp_path):
    async def fake_download(key, path):
        open(path, "wb").write(b"cached")
        return True

    ffmpeg = AsyncMock()
    with patch("app.storage.download_file", AsyncMock(side_effect=fake_download)) as dl, \
         patch("app.audio_utils._ffmpeg", ffmpeg):
        music = await background_music._separate(tmp_path / "src.wav", tmp_path, "bgm/7/abc")
    assert music == tmp_path / "bgm_music.mp3"
    assert dl.await_count == 2                  # music + vocals
    ffmpeg.assert_not_awaited()                 # khong chuyen ma, khong goi Modal


async def test_mix_cuts_music_on_input_without_intermediate_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "bgm_ducking", False)
    music = tmp_path / "bgm_music.mp3"
    music.write_bytes(b"m")
    dub = tmp_path / "d.mp3"
    dub.write_bytes(b"dub")
    calls = []

    async def fake_ffmpeg(*args):
        calls.append(args)
        open(args[-1], "wb").write(b"x")

    task = asyncio.create_task(asyncio.sleep(0, music))
    with patch("app.audio_utils._ffmpeg", AsyncMock(side_effect=fake_ffmpeg)):
        await background_music.mix_into_chunk(dub, task, 600, 1200, tmp_path)
    assert len(calls) == 1                      # 1 luot FFmpeg duy nhat cho buoc tron
    assert ["-ss", "600.000", "-to", "1200.000"] == list(calls[0][2:6])


async def test_b2_upload_runs_in_background_and_does_not_block_mix(tmp_path, monkeypatch):
    """Job 40: bước trộn chờ thêm ~150 s vì đợi upload cache lên B2. Giờ upload chạy nền."""
    gate = asyncio.Event()

    async def slow_upload(path, key, **kw):
        await gate.wait()
        return "url"

    class _Fn:
        class remote:
            @staticmethod
            async def aio(audio, suffix):
                return {"music": b"m", "vocals": b"v", "separate_sec": 1.0}

    fake_modal = type("M", (), {"Function": type("F", (), {"from_name": staticmethod(lambda a, b: _Fn)})})
    (tmp_path / "src.wav").write_bytes(b"x")

    async def fake_ffmpeg(*args):
        open(args[-1], "wb").write(b"mp3")

    with patch.dict("sys.modules", {"modal": fake_modal}), \
         patch("app.audio_utils._ffmpeg", AsyncMock(side_effect=fake_ffmpeg)), \
         patch("app.storage.download_file", AsyncMock(return_value=False)), \
         patch("app.storage.upload_file", AsyncMock(side_effect=slow_upload)) as up:
        music = await asyncio.wait_for(background_music._separate(tmp_path / "src.wav", tmp_path, "bgm/1/x"), 2)
        assert music is not None                       # tra ve ngay, khong cho upload
        assert background_music._pending_uploads
        gate.set()
        await background_music.wait_pending_uploads(2)
    assert up.await_count == 2
    assert not background_music._pending_uploads


async def test_warm_up_skipped_when_disabled_or_cached(monkeypatch):
    monkeypatch.setattr(settings, "bgm_separation", "")
    assert background_music.warm_up(1, "u") is None

    monkeypatch.setattr(settings, "bgm_separation", "modal")
    with patch("app.storage.exists", AsyncMock(return_value=True)):
        task = background_music.warm_up(1, "https://youtu.be/x")
        await task                                    # da co nhac tren B2 -> khong goi Modal (khong loi)


async def test_warm_up_sends_empty_audio_to_modal(monkeypatch):
    monkeypatch.setattr(settings, "bgm_separation", "modal")
    calls = []

    class _Fn:
        class remote:
            @staticmethod
            async def aio(audio, suffix):
                calls.append(audio)
                return {"warm": True}

    fake_modal = type("M", (), {"Function": type("F", (), {"from_name": staticmethod(lambda a, b: _Fn)})})
    with patch.dict("sys.modules", {"modal": fake_modal}), \
         patch("app.storage.exists", AsyncMock(return_value=False)):
        await background_music.warm_up(1, "https://youtu.be/x")
    assert calls == [b""]
