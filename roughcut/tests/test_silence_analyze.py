from __future__ import annotations

from silence.analyze import parse_silencedetect


def test_parse_silencedetect_handles_leading_internal_and_trailing():
    log = """
    [silencedetect] silence_start: 0
    [silencedetect] silence_end: 3.2 | silence_duration: 3.2
    [silencedetect] silence_start: 8.5
    [silencedetect] silence_end: 10.0 | silence_duration: 1.5
    [silencedetect] silence_start: 18.0
    """
    result = parse_silencedetect(log, 20.0)
    assert [(item.start_s, item.end_s) for item in result] == [
        (0.0, 3.2),
        (8.5, 10.0),
        (18.0, 20.0),
    ]


def test_parse_silencedetect_accepts_silence_already_in_progress():
    result = parse_silencedetect("silence_end: 1.25 | silence_duration: 1.25", 8.0)
    assert [(item.start_s, item.end_s) for item in result] == [(0.0, 1.25)]

