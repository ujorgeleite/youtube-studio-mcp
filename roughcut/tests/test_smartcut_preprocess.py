import subprocess

from smartcut.preprocess import _loudnorm_stats, has_audio_stream


def test_loudnorm_stats_extracts_the_final_json_object():
    stats = _loudnorm_stats('noise\n{ "input_i": "-20.0", "input_lra": "4.0", "input_tp": "-2.0", "input_thresh": "-30.0", "target_offset": "0.2" }\n')
    assert stats["input_i"] == "-20.0"


def test_has_audio_stream_checks_ffprobe_output(monkeypatch):
    monkeypatch.setattr("smartcut.preprocess.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "0\n", ""))
    assert has_audio_stream("with-audio.mp4") is True

    monkeypatch.setattr("smartcut.preprocess.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""))
    assert has_audio_stream("silent-video.mp4") is False
