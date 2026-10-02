import json
from pathlib import Path
from xml.etree import ElementTree as ET

from core.project import ReviewState
from core.schema import Inventory, OutputFormat, Proposal, Transcript, Word
from montage import delivery, render
from montage.plan import build_edit_plan
from montage.timeline import path_url, timebase, write_xmeml
from tests.test_montage import _takes, _video


def test_timebase_marks_ntsc_rates():
    assert timebase(29.97) == (30, True) and timebase(25) == (25, False)


def test_path_url_encodes_spaces_and_accents():
    assert path_url("/Vídeos/dia no parque.mp4") == "file://localhost/V%C3%ADdeos/dia%20no%20parque.mp4"


def test_xmeml_has_main_broll_and_ambient_tracks(tmp_path: Path):
    plan = build_edit_plan("A", _video(), _takes(), output=OutputFormat(1920, 1080, 25))
    target = write_xmeml(plan, _takes(), tmp_path / "t.xml")
    assert target.read_text().startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>')
    root = ET.parse(target).getroot()
    video_tracks = root.findall("./sequence/media/video/track")
    audio_tracks = root.findall("./sequence/media/audio/track")
    assert [len(track.findall("clipitem")) for track in video_tracks] == [3, 1]
    assert [len(track.findall("clipitem")) for track in audio_tracks] == [2]
    first = video_tracks[0].find("clipitem")
    assert [first.findtext(tag) for tag in ("start", "end", "in", "out")] == ["0", "75", "25", "100"]
    assert first.find("file/pathurl").text.endswith("b_conversa.mp4")
    assert len(root.findall(".//file/pathurl")) == 2
    assert root.findtext("./sequence/duration") == "150"


def test_ambient_gain_is_written_as_linear_level(tmp_path: Path):
    takes = _takes()
    takes[1].has_audio = True
    plan = build_edit_plan("A", _video(), takes)
    root = ET.parse(write_xmeml(plan, takes, tmp_path / "t.xml")).getroot()
    levels = [float(value.text) for value in root.iter("value")]
    assert levels and abs(levels[0] - 0.0794) < 0.001


def test_deliver_writes_the_whole_package(media_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(render, "video_encoder", lambda: ["-c:v", "libx264", "-preset", "ultrafast"])
    monkeypatch.setattr(delivery, "build_edit_plan", lambda *a, **k: build_edit_plan(*a, output=OutputFormat(320, 180, 25), **k))
    takes = _takes(media_dir)
    inventory = Inventory(takes=takes, transcripts={"T01": Transcript("T01", words=[Word(1.2, 1.8, "Olá.")])})
    video = _video()
    proposal = Proposal("A", "Teste", videos=[video])
    review = ReviewState(excluded=["a1.b02"])
    events = []
    artifacts = delivery.deliver(proposal, video, inventory, review, tmp_path / "entrega", tmp_path / "work",
                                 progress=lambda fraction, message: events.append(fraction))
    assert set(artifacts) == {"video", "plan", "report", "subtitles", "timeline"}
    assert all(Path(path).is_file() for path in artifacts.values())
    assert Path(artifacts["video"]).name == "teste__montagem.mp4"
    plan = json.loads(Path(artifacts["plan"]).read_text())
    assert plan["excluded"] == ["a1.b02"] and len(plan["beats"]) == 2
    assert "Olá." in Path(artifacts["subtitles"]).read_text()
    assert events[-1] == 1.0 and events == sorted(events)


def test_slugify():
    assert delivery.slugify("A adaptação acontece nos dias comuns!") == "a-adaptacao-acontece-nos-dias-comuns"
