from __future__ import annotations

from silence.analyze import extract_thumbnail, parse_silencedetect
from tests.fixtures.make_clips import make_clips


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


def test_extract_thumbnail_creates_jpeg_without_touching_video(tmp_path):
    source = make_clips(str(tmp_path / "raw"))["C01"]
    source_mtime = (tmp_path / "raw" / "C01.mp4").stat().st_mtime_ns

    thumbnail = extract_thumbnail(source, tmp_path / "thumbs" / "C01.jpg", duration_s=5)

    assert thumbnail.is_file()
    assert thumbnail.stat().st_size > 0
    assert (tmp_path / "raw" / "C01.mp4").stat().st_mtime_ns == source_mtime
