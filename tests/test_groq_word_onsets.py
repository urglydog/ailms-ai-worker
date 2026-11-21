"""Mốc bắt đầu câu lấy theo từ đầu tiên (nhạc intro không bị lời lồng tiếng nói đè)."""

from app.providers import groq_asr


def _payload(segments, words):
    return {"text": "x", "language": "en", "duration": 30.0, "segments": segments, "words": words}


def test_segment_start_snaps_to_first_word_after_intro():
    res = groq_asr._parse_response(_payload(
        [{"start": 0.0, "end": 9.0, "text": "Hi, I'm Carrie-Anne"}, {"start": 9.0, "end": 12.0, "text": "next"}],
        [{"word": "Hi", "start": 4.2, "end": 4.5}, {"word": "I'm", "start": 4.6, "end": 4.8},
         {"word": "next", "start": 9.3, "end": 9.8}],
    ))
    assert [s.start for s in res.segments] == [4.2, 9.3]
    assert [s.end for s in res.segments] == [9.0, 12.0]


def test_segment_without_words_keeps_original_start():
    res = groq_asr._parse_response(_payload([{"start": 2.0, "end": 5.0, "text": "hello"}], []))
    assert res.segments[0].start == 2.0


def test_word_slightly_before_segment_does_not_move_start_backwards():
    res = groq_asr._parse_response(_payload(
        [{"start": 5.0, "end": 8.0, "text": "a"}], [{"word": "a", "start": 4.97, "end": 5.2}],
    ))
    assert res.segments[0].start == 5.0
