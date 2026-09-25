from pathlib import Path

from smartcut.pipeline import analyze_clip, default_output_dir
from smartcut.schema import SpeechRegion, Word


def test_pipeline_reuses_vad_and_transcript_cache(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    out = tmp_path / "result"
    monkeypatch.setattr("smartcut.pipeline.probe_duration", lambda _: 10.0)
    monkeypatch.setattr("smartcut.pipeline.speech_regions", lambda _: [SpeechRegion(0, 10)])
    monkeypatch.setattr("smartcut.pipeline.transcribe_words", lambda _: [Word(0, 1, "Oi."), Word(3, 4, "Tudo")])

    plan, artifacts = analyze_clip(source, out)
    assert len(plan.cuts) == 1
    assert all(path.is_file() for path in artifacts.values())
    assert artifacts["plan"].parent.name == "plans"
    assert artifacts["srt"].parent.name == "subtitles"
    assert artifacts["report"].parent.name == "reports"
    assert artifacts["fcpxml"].parent.name == "timelines"

    monkeypatch.setattr("smartcut.pipeline.speech_regions", lambda _: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("smartcut.pipeline.transcribe_words", lambda _: (_ for _ in ()).throw(AssertionError()))
    cached, _ = analyze_clip(source, out)
    assert len(cached.cuts) == 1


def test_default_output_is_a_sibling_folder(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    assert default_output_dir(raw) == tmp_path / "raw__corte-inteligente"


def test_pipeline_can_analyze_preprocessed_audio_but_keeps_original_as_source(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"; audio = tmp_path / "normalized.m4a"
    source.write_bytes(b"video"); audio.write_bytes(b"audio")
    monkeypatch.setattr("smartcut.pipeline.probe_duration", lambda _: 5.0)
    seen = []
    monkeypatch.setattr("smartcut.pipeline.speech_regions", lambda path: seen.append(Path(path)) or [])
    monkeypatch.setattr("smartcut.pipeline.transcribe_words", lambda path: [])
    plan, _ = analyze_clip(source, tmp_path / "result", analysis_source=audio)
    assert plan.source == str(source)
    assert seen == [audio]
