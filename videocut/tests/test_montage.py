import subprocess
from pathlib import Path

import pytest

from core.project import ReviewState
from core.schema import Beat, OutputFormat, Overlay, StoryVideo, Take, Transcript, Word
from media.probe import probe
from montage import render
from montage.plan import build_edit_plan, choose_format, ordered_beats
from montage.report import editorial_report
from montage.subtitles import build_cues, timeline_words, write_srt
from tests.story_fixtures import example_inventory
from tests.test_story import FULL, _single
from story.validate import build_report


def _video() -> StoryVideo:
    return StoryVideo("a1", "Teste", "mensagem", [
        Beat("a1.b01", "Fala", "gancho", "T01", 1, 4, overlays=[Overlay("T02", 0.5, 2, at_s=1)]),
        Beat("a1.b02", "Ação", "desenvolvimento", "T02", 1, 3, audio="ambiente"),
        Beat("a1.b03", "Fim", "conclusao", "T01", 4.5, 5.5),
    ])


def _takes(folder: Path | None = None) -> list[Take]:
    base = folder or Path("/raw")
    return [Take("T01", str(base / "b_conversa.mp4"), "b_conversa.mp4", 6, 320, 240, 25, True),
            Take("T02", str(base / "a_passeio.mov"), "a_passeio.mov", 4, 320, 240, 25, False)]


def test_review_order_and_exclusions_drive_the_sequence():
    review = ReviewState(order=["a1.b03", "a1.b01"], excluded=["a1.b02"])
    assert [beat.id for beat in ordered_beats(_video(), review)] == ["a1.b03", "a1.b01"]
    assert [beat.id for beat in ordered_beats(_video(), None)] == ["a1.b01", "a1.b02", "a1.b03"]


def test_plan_keeps_image_and_audio_tracks_separate():
    plan = build_edit_plan("A", _video(), _takes())
    assert [(c.take_id, c.timeline_in) for c in plan.main_track] == [("T01", 0), ("T02", 3), ("T01", 5)]
    assert [(c.take_id, c.timeline_in, c.duration_s) for c in plan.broll_track] == [("T02", 1, 1.5)]
    assert [(c.take_id, c.role) for c in plan.audio] == [("T01", "fala"), ("T01", "fala")]
    assert plan.duration_s == 6


def test_format_follows_majority_orientation_and_fps():
    takes = [Take("T01", "/a", "a", 60, 1080, 1920, 29.97), Take("T02", "/b", "b", 60, 1920, 1080, 60)]
    beats = [Beat("b1", "x", "gancho", "T01", 0, 40), Beat("b2", "y", "apoio", "T02", 0, 10)]
    fmt = choose_format(takes, beats)
    assert (fmt.width, fmt.height, fmt.fps) == (1080, 1920, 29.97)
    assert render.frame_rate(29.97) == "30000/1001" and render.frame_rate(25) == "25"


def test_subtitles_are_remapped_to_the_montage_timeline(tmp_path: Path):
    plan = build_edit_plan("A", _video(), _takes())
    transcripts = {"T01": Transcript("T01", words=[Word(1.2, 1.6, "Olá"), Word(1.7, 2.0, "gente."), Word(4.6, 5.0, "Tchau.")])}
    assert timeline_words(plan, transcripts) == [(0.2, 0.6, "Olá"), (0.7, 1.0, "gente."), (5.1, 5.5, "Tchau.")]
    assert [cue.text for cue in build_cues(timeline_words(plan, transcripts))] == ["Olá gente.", "Tchau."]
    srt = write_srt(plan, transcripts, tmp_path / "a.srt").read_text()
    assert "00:00:05,100 --> 00:00:05,500\nTchau." in srt


def test_segment_command_overlays_broll_and_mixes_audio():
    plan = build_edit_plan("A", _video(), _takes(), output=OutputFormat(320, 180, 25))
    command = render.segment_command(render.segments(plan)[0], plan, ["-c:v", "libx264"])
    graph = command[command.index("-filter_complex") + 1]
    assert command.count("-i") == 3
    assert "overlay=eof_action=pass:enable='between(t,1.000,2.500)'" in graph
    assert "amix=inputs=2" in graph and "afade=t=in" in graph


def test_render_produces_final_video_with_expected_duration(media_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(render, "video_encoder", lambda: ["-c:v", "libx264", "-preset", "ultrafast"])
    plan = build_edit_plan("A", _video(), _takes(media_dir), output=OutputFormat(320, 180, 25))
    events = []
    output = render.render_plan(plan, tmp_path / "videos" / "montagem.mp4", tmp_path / "work",
                                progress=lambda fraction, message: events.append(message))
    info = probe(output)
    assert info.duration_s == pytest.approx(6, abs=0.15)
    assert (info.width, info.height, info.fps, info.has_audio) == (320, 180, 25.0, True)
    assert events[-1] == "Montagem concluída"
    segments = list((tmp_path / "work" / "segments").glob("*.mp4"))
    assert len(segments) == 3

    reordered = build_edit_plan("A", _video(), _takes(media_dir), ReviewState(order=["a1.b03", "a1.b01", "a1.b02"]), OutputFormat(320, 180, 25))
    render.render_plan(reordered, tmp_path / "videos" / "reordenado.mp4", tmp_path / "work")
    assert len(list((tmp_path / "work" / "segments").glob("*.mp4"))) == 3


def test_render_rejects_empty_plan(tmp_path: Path):
    from media.probe import MediaError
    empty = build_edit_plan("A", _video(), _takes(), ReviewState(excluded=["a1.b01", "a1.b02", "a1.b03"]))
    with pytest.raises(MediaError):
        render.render_plan(empty, tmp_path / "x.mp4", tmp_path)


def test_editorial_report_lists_blocks_evidence_and_exclusions():
    inventory = example_inventory()
    proposal = build_report(_single(FULL), inventory).proposals[0]
    video = proposal.videos[0]
    review = ReviewState(excluded=[video.beats[2].id])
    plan = build_edit_plan(proposal.id, video, inventory.takes, review)
    text = editorial_report(proposal, video, plan, inventory, review)
    assert "## Sequência" in text and "“É nessas coisas pequenas" in text
    assert "## Excluídos na revisão" in text and "O passeio" in text.split("## Excluídos")[1]
    assert "✓ **Mensagem central**" in text
