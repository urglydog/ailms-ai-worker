"""Chạy thử run_experiment_v2 KHÔNG gọi API (giả lập Groq, Gemini, Azure, Redis). Chỉ để kiểm tra code.
    python NCKH/experiments/_smoke_v2.py
"""
import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from pydub import AudioSegment  # noqa: E402
from pydub.generators import Sine  # noqa: E402

import run_experiment_v2 as R  # noqa: E402
from app.providers import groq_asr  # noqa: E402
from app.services import dubbing_service  # noqa: E402

_cps = {"v": None}


async def fake_transcribe(path):
    segs = [SimpleNamespace(start=1.0 + 3 * i, end=1.0 + 3 * i + (0.8 if i == 2 else 2.5), text=t)
            for i, t in enumerate(["Hello students.", "Today we learn TCP.", "Thanks.", ".", "UDP is fast and simple to use.", "TCP guarantees ordered and reliable delivery of every single packet across the network."])]
    return SimpleNamespace(language="english", duration_sec=20.0, segments=segs,
                           speech_duration_sec=sum(s.end - s.start for s in segs))


async def fake_generate(prompt, **kw):
    body = prompt.split("## INPUT", 1)[1].split("## Output", 1)[0]
    data = json.loads(body)
    out = {}
    for k, v in data.items():
        text = v["text"] if isinstance(v, dict) else v
        lim = v.get("max_chars") if isinstance(v, dict) else None
        vi = ("Xin chao cac ban sinh vien than men " + text) if "max_chars" not in prompt else ("Ban dich " + text)
        out[k] = vi[:lim] if lim else vi
    return SimpleNamespace(text=json.dumps(out))


async def fake_synth(text, voice, path, rate=None):
    sec = max(0.3, len(text) / 12.0)
    Sine(300).to_audio_segment(duration=int(sec * 1000)).export(path, format="mp3")
    from decimal import Decimal
    return R.azure_tts.SynthesisResult(file_path=path, duration_sec=sec, applied_rate=Decimal("1.0"))


async def fake_get_cps(voice):
    return _cps["v"]


async def fake_rec(voice, texts, results):
    _cps["v"] = 12.0


async def main():
    groq_asr.transcribe = fake_transcribe
    R._orig_generate = fake_generate
    R._orig_synth = fake_synth
    dubbing_service._voice_chars_per_sec = fake_get_cps
    dubbing_service._record_voice_chars_per_sec = fake_rec
    R.install_counters()

    tmp = Path(tempfile.mkdtemp())
    src = tmp / "a.mp3"
    AudioSegment.silent(duration=20000).export(src, format="mp3")
    spec = R.VideoSpec(id="smoke", source=str(src), voice_name="vi-VN-HoaiMyNeural", category="test")
    for run in ("r1", "r2"):
        rows, vrow = await R.run_video(spec, R.ALL_VARIANTS, run, tmp / run, tmp / "cache", None, True)
        R._write_csv(tmp / run / "segments.csv", rows, append=False)
        R._write_csv(tmp / run / "videos.csv", [vrow], append=False)
        print(run, len(rows), "rows;", {k: v for k, v in vars(vrow).items() if k.startswith(("llm", "tts", "cps", "n_"))})
        for r in rows:
            print("  ", r.variant, r.seq, r.t_orig, r.t_tts_default, r.branch, r.applied_rate, r.t_final)
    print("TMP", tmp)


asyncio.run(main())
