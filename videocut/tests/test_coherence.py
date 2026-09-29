from core.schema import Beat, Evidence, Inventory, Overlay, StoryVideo, Transcript, Word
from story.coherence import SceneRules, tidy


def _inventory():
    words = [Word(i * 0.5, i * 0.5 + 0.4, f"palavra{i}") for i in range(80)]
    return Inventory(transcripts={"T01": Transcript("T01", words=words), "T02": Transcript("T02", words=words)})


def _beat(beat_id, take, start, end, role="desenvolvimento", overlays=None):
    return Beat(beat_id, beat_id, role, take, start, end, overlays=overlays or [], evidence=[Evidence(take, start, end, "x y z w", "cena")])


def test_same_take_neighbors_merge_and_overlaps_disappear():
    video = StoryVideo("a1", "V", beats=[
        _beat("b1", "T01", 0, 7.2, "gancho"), _beat("b2", "T01", 6.9, 12.6, overlays=[Overlay("T02", 1, 3, 1)]),
        _beat("b3", "T01", 13.5, 20), _beat("b4", "T02", 0, 10), _beat("b5", "T02", 30, 38, "conclusao")])
    notes = tidy(video, _inventory(), SceneRules())
    assert [(b.take_id, b.start_s, b.end_s) for b in video.beats] == [("T01", 0, 20), ("T02", 0, 10), ("T02", 30, 38)]
    assert video.beats[0].role == "gancho" and video.beats[0].overlays[0].at_s == 8.2
    assert "palavra0" in video.beats[0].evidence[0].quote and "palavra25" in video.beats[0].evidence[0].quote
    assert any("unidos" in note for note in notes) and any("sobreposição" in note for note in notes)


def test_fragments_leave_and_edge_roles_are_unique():
    video = StoryVideo("a1", "V", beats=[
        _beat("b1", "T01", 0, 10), _beat("b2", "T02", 0, 1.5), _beat("b3", "T01", 30, 40, "conclusao"),
        _beat("b4", "T02", 20, 30, "gancho"), _beat("b5", "T01", 60, 70)])
    tidy(video, _inventory(), SceneRules())
    assert [b.id for b in video.beats] == ["b1", "b3", "b4", "b5"]
    assert [b.role for b in video.beats] == ["desenvolvimento", "desenvolvimento", "desenvolvimento", "conclusao"]


def test_rules_come_from_the_style_file():
    rules = SceneRules.load()
    assert rules.merge_gap_s == 2.0 and rules.min_block_s == 2.5 and rules.unique_edge_roles
