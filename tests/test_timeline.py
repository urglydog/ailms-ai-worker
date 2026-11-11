"""BR-CHUNK-05 (sửa 11/11/2026): ghép câu theo mốc tuyệt đối, không cộng dồn độ trễ.

Bối cảnh: đo NCKH cho thấy cách cũ (khoảng lặng cố định start_i − end_{i-1}) làm audio
bài 15 phút dài hơn video 96 s. Các test dưới đây khoá lại hành vi mới.
"""

from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from app import audio_utils
from app.services.dubbing_service import clamp_stt_segments

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="can ffmpeg")


# ---------------------------------------------------------------- plan_onsets (thuần)
def test_onsets_keep_original_when_everything_fits():
    assert audio_utils.plan_onsets([0.0, 3.0, 6.0], [2.0, 2.0, 2.0]) == [0.0, 3.0, 6.0]


def test_overrun_never_overlaps_next_sentence():
    onsets = audio_utils.plan_onsets([0.0, 2.0, 4.0], [3.0, 1.0, 1.0])
    assert onsets[1] == 3.0          # lùi tới khi câu trước nói xong, không chồng
    assert onsets[2] == 4.0          # khoảng lặng phía sau hấp thụ trễ -> về đúng mốc gốc


def test_delay_does_not_accumulate_across_long_gap():
    # cách cũ: mỗi câu tràn 1 s -> câu thứ 4 trễ 3 s. Cách mới: gặp khoảng lặng dài thì hết trễ.
    onsets = audio_utils.plan_onsets([0.0, 2.0, 4.0, 20.0], [3.0, 3.0, 3.0, 1.0])
    assert onsets == [0.0, 3.0, 6.0, 20.0]


def test_negative_desired_onset_is_clamped_to_zero():
    assert audio_utils.plan_onsets([-0.5], [1.0]) == [0.0]


# ---------------------------------------------------------------- clamp ASR (E6)
def _s(start, end, text="x"):
    return SimpleNamespace(start=start, end=end, text=text)


def test_clamp_drops_segment_starting_after_audio_and_trims_end():
    segs = [_s(0.0, 2.0), _s(709.44, 739.42, "Thank you."), _s(720.0, 725.0)]
    out = clamp_stt_segments(segs, 718.0)
    assert out == [(0.0, 2.0, "x"), (709.44, 718.0, "Thank you.")]


def test_clamp_drops_empty_text_and_zero_length():
    assert clamp_stt_segments([_s(1.0, 1.01), _s(2.0, 3.0, "  ")], 10.0) == []


# ---------------------------------------------------------------- place_on_timeline (cần ffmpeg)
def _tone(tmp_path, name, sec):
    p = tmp_path / f"{name}.mp3"
    Sine(440).to_audio_segment(duration=int(sec * 1000)).export(str(p), format="mp3")
    return p


@needs_ffmpeg
@pytest.mark.asyncio
async def test_chunk_output_is_exactly_chunk_length_when_short(tmp_path):
    paths = [_tone(tmp_path, "a", 1.0), _tone(tmp_path, "b", 1.0)]
    out = tmp_path / "chunk.mp3"
    res = await audio_utils.place_on_timeline(paths, [0.0, 5.0], 10.0, out)
    assert res.tempo_applied == 1.0
    assert abs(len(AudioSegment.from_file(out)) / 1000 - 10.0) < 0.1


@needs_ffmpeg
@pytest.mark.asyncio
async def test_overlong_chunk_is_sped_up_and_fitted(tmp_path):
    # 3 câu 4 s dồn vào khung 10 s -> thô 12 s -> tăng tốc x1.15, phần dư cắt, đúng 10 s
    paths = [_tone(tmp_path, f"s{i}", 4.0) for i in range(3)]
    out = tmp_path / "chunk.mp3"
    res = await audio_utils.place_on_timeline(paths, [0.0, 3.0, 6.0], 10.0, out)
    assert res.raw_length_sec == pytest.approx(12.0, abs=0.1)
    assert res.tempo_applied == pytest.approx(audio_utils.MAX_CHUNK_TEMPO)
    assert res.max_delay_sec == pytest.approx(2.0, abs=0.1)
    assert abs(len(AudioSegment.from_file(out)) / 1000 - 10.0) < 0.1
